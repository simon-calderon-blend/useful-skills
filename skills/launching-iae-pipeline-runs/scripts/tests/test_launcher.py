import csv
import json
from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from botocore.stub import ANY

from iae_launch import api, auth, dispatch, envs, launcher, runner
from iae_launch import plan as plan_mod
from iae_launch.live import Deployed, LivePaths
from tests.test_checks_env import jwt

DISPATCH_DOC = {"version": "1", "values": {"dispatch": {"enabled": True, "maxMessagesPerCycle": 10}}}
VERSIONS = {"api/storage": 6, "throttle-controller/dispatch": 9}
ACCOUNT = "072055531089"
BUCKET = "adr-dev-medicalaudit-workarea"
API_URL = "https://abc.execute-api.us-east-1.amazonaws.com/v1"


def deployed(enabled=True):
    doc = json.loads(json.dumps(DISPATCH_DOC))
    doc["values"]["dispatch"]["enabled"] = enabled
    return Deployed("app", "env", "prof", 9, 1, doc)


def live_paths(enabled=True, versions=None, in_progress=None):
    return LivePaths("audit-processes", "raw/", "s/", "c/", "raw/", {"raw/": {}, "s/": {}}, "q", [], 100,
                     deployed(enabled), versions=versions or dict(VERSIONS), in_progress=in_progress or {})


def make_plan(tmp_path, *, was_enabled=True, restore_to=True, claims_n=2, env="dev", mutate=None):
    src = tmp_path / "src"
    src.mkdir(exist_ok=True)
    claims = []
    for n in range(claims_n):
        f = src / f"f{n}.pdf"
        f.write_bytes(b"x")
        claims.append({"folder": f"{n}_{100 + n}", "body": {"idReclamacion": 100 + n},
                       "seed_items": [
                           {"kind": "put", "source": str(f), "dest_suffix": f"raw/f{n}.pdf",
                            "content_type": "application/pdf", "size": 1},
                           {"kind": "copy", "source": f"s3://{BUCKET}/audit-processes/old/k.json", "dest_suffix": "s/k.json",
                            "content_type": "application/json"}]})
    spec = envs.get_env(env if env in envs.ENVS else "dev")
    p = {"env": env, "profile": spec.profile, "account_id": spec.account_id, "run_id": "skill-1",
         "created_at": "2026-11-09T12:00:00+00:00",
         "live": {"paths": {}, "versions": dict(VERSIONS),
                  "api_base_url": "https://abc.execute-api.us-east-1.amazonaws.com/v1",
                  "state_machine_arn": "arn:sm", "workarea_bucket": f"adr-{env}-medicalaudit-workarea",
                  "base_prefix": "audit-processes"},
         "decisions": {"source_dir": str(src)}, "claims": claims,
         "dispatch": {"was_enabled": was_enabled, "closed_by_marker": False, "restore_to": restore_to}}
    if mutate:
        mutate(p)
    p["plan_id"] = plan_mod.compute_plan_id(p)
    path = tmp_path / "runs" / "skill-1" / "plan.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(p))
    return path, p


class FakeApi:
    def __init__(self, results=None, probe=404):
        self.results, self.probe, self.posted = list(results or []), probe, []

    def post(self, factory, base, token, body):
        self.posted.append(body)
        r = self.results.pop(0) if self.results else api.IniciarResult(
            True, f"pid{len(self.posted)}", "RECIBIDO", "ok")
        if isinstance(r, Exception):
            raise r
        return r

    def probe_fn(self, factory, base, token, probe_id):
        return self.probe


def good_token(env="dev"):
    return auth.Token(jwt({"aud": envs.expected_audience(env), "exp": 4102444800}))


class Harness:
    def __init__(self, stubbed, tmp_path, *, enabled=True, live=None, account=ACCOUNT, secret="s",
                 env="dev", api_obj=None, token=None):
        self.sts, self.ac, self.s3 = stubbed("sts"), stubbed("appconfig"), stubbed("s3")
        self.logs = stubbed("logs")
        self.sts.ok("get_caller_identity", {"Account": account, "Arn": "arn:aws:iam::123456789012:user/x",
                                             "UserId": "u"})
        self.api = api_obj or FakeApi()
        self.tunnel_opened = self.tunnel_closed = 0
        self.live = live or live_paths(enabled)
        self.sleeps = []
        self.token_calls = 0
        tok = token or good_token(env)

        def token_fn(spec, secret_):
            self.token_calls += 1
            return tok
        harness = self

        @contextmanager
        def open_tunnel(host):
            harness.tunnel_opened += 1
            try:
                yield type("T", (), {"connection_factory": staticmethod(lambda *a: None)})()
            finally:
                harness.tunnel_closed += 1
        self.deps = launcher.Deps(
            clients=runner.Clients(sts=self.sts.client, appconfig=self.ac.client, s3=self.s3.client,
                                   logs=self.logs.client),
            environ={"IAE_CLIENT_SECRET": secret} if secret else {},
            token_fn=token_fn, open_tunnel=open_tunnel, post_fn=self.api.post, probe_fn=self.api.probe_fn,
            gather=lambda: self.live, reload_dispatch=lambda: self.live.dispatch, api_url=lambda: API_URL,
            sleep=self.sleeps.append, clock=lambda: 0.0, state_home=tmp_path / "state",
            now=lambda: datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc))

    def expect_strategy(self):
        self.ac.ok("list_deployment_strategies", {"Items": [
            {"Id": "strat", "Name": "adr-appconfig-seed-nobake", "DeploymentDurationInMinutes": 0,
             "FinalBakeTimeInMinutes": 0}]})

    def expect_dispatch_flip(self, enabled, version, deployment):
        d = deployed(not enabled)
        self.ac.ok("create_hosted_configuration_version",
                   {"VersionNumber": version, "ContentType": "application/json"},
                   ApplicationId="app", ConfigurationProfileId="prof",
                   Content=dispatch.build_content(d, enabled), ContentType="application/json")
        self.ac.ok("start_deployment", {"DeploymentNumber": deployment}, ApplicationId="app",
                   EnvironmentId="env", DeploymentStrategyId="strat", ConfigurationProfileId="prof",
                   ConfigurationVersion=str(version))
        self.ac.ok("get_deployment", {"State": "COMPLETE"}, ApplicationId="app", EnvironmentId="env",
                   DeploymentNumber=deployment)

    def expect_off(self, start_ms=None):
        """El throttle controller ya vio el flag apagado (línea OFF en sus logs)."""
        from botocore.stub import ANY as _ANY
        self.logs.ok("filter_log_events", {"events": [
            {"message": "Dispatch feature flag is OFF", "timestamp": 1}]},
            logGroupName="/aws/lambda/adr-dev-medicalaudit-api-throttle-controller",
            startTime=start_ms if start_ms is not None else _ANY,
            filterPattern='"Dispatch feature flag is OFF"')

    def expect_latest_deployment_time(self):
        self.ac.ok("list_deployments", {"Items": [{"DeploymentNumber": 3, "ConfigurationName": "dispatch", "State": "COMPLETE"}]},
                   ApplicationId="app", EnvironmentId="env")
        self.ac.ok("get_deployment", {"DeploymentNumber": 3, "State": "COMPLETE",
                                      "CompletedAt": datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)},
                   ApplicationId="app", EnvironmentId="env", DeploymentNumber=3)

    def expect_puts(self, n_claims):
        for _ in range(n_claims):
            self.s3.ok("put_object", {}, Bucket=BUCKET, Key=ANY, Body=ANY, ContentType="application/pdf")
            self.s3.ok("copy_object", {}, Bucket=BUCKET, Key=ANY,
                       CopySource={"Bucket": BUCKET, "Key": "audit-processes/old/k.json"},
                       ContentType="application/json", MetadataDirective="REPLACE")

    def run(self, plan_path, plan, **kw):
        kw.setdefault("settle_seconds", 75)
        return launcher.execute_plan(plan_path, plan["plan_id"], self.deps, **kw)


def breadcrumb(tmp_path):
    return tmp_path / "state" / "launching-iae-pipeline-runs" / "paused-dev.json"


def happy_expectations(h, n_claims=2):
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off(int(datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).timestamp() * 1000))
    h.expect_puts(n_claims)
    h.expect_dispatch_flip(True, 13, 14)


def test_happy_path(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path)
    happy_expectations(h)
    out = h.run(path, plan)
    assert out.exit_code == 0
    rep = json.loads((tmp_path / "runs" / "skill-1" / "launch_report.json").read_text())
    assert [c["pid"] for c in rep["claims"]] == ["pid1", "pid2"] and rep["failures"] == []
    assert rep["dispatch"] == {"before": True, "after": True, "restore_to": True}
    assert rep["opened_dispatch"] is False
    rows = list(csv.DictReader((tmp_path / "runs" / "skill-1" / "process_index.csv").open()))
    assert [(r["radicado"], r["pid"], r["descargado"]) for r in rows] == [
        ("0_100", "pid1", "false"), ("1_101", "pid2", "false")]
    assert rows[0]["s3uri"] == f"s3://{BUCKET}/audit-processes/pid1/"
    assert 75 in h.sleeps and h.tunnel_opened == h.tunnel_closed == 1
    assert not breadcrumb(tmp_path).exists()
    assert [b["idReclamacion"] for b in h.api.posted] == [100, 101]


def test_post_rejection_continues_and_exit_3(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, api_obj=FakeApi([api.IniciarResult(False, "old", "ERROR", "Ya existe"),
                                                   api.IniciarResult(True, "pid2", "RECIBIDO", "ok")]))
    happy_expectations(h, 1)
    out = h.run(path, plan)
    assert out.exit_code == 3
    rep = out.report
    assert rep["failures"][0]["folder"] == "0_100" and "Ya existe" in rep["failures"][0]["detail"]
    assert rep["failures"][0]["pid"] == "old"
    assert [c["folder"] for c in rep["claims"] if c["status"] == "launched"] == ["1_101"]


def test_api_error_continues(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, api_obj=FakeApi([api.ApiError(400, "bad field")]))
    happy_expectations(h, 1)
    out = h.run(path, plan)
    assert out.exit_code == 3 and "bad field" in out.report["failures"][0]["detail"]


def test_seed_failure_holds_dispatch_closed_and_keeps_breadcrumb(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.s3.err("put_object", "InternalError", Bucket=BUCKET, Key=ANY, Body=ANY,
             ContentType="application/pdf")
    out = h.run(path, plan)            # sin flip de restauración: el dispatch NO se abre
    assert out.exit_code == 3
    assert out.report["failures"][0]["status"] == "seed_failed" and out.report["failures"][0]["pid"] == "pid1"
    assert out.report["held_closed"] is True and "--stop-run" in out.report["hint"]
    assert out.report["dispatch"]["after"] is False and out.report["opened_dispatch"] is False
    assert breadcrumb(tmp_path).exists() and h.tunnel_closed == 1


def test_keyboard_interrupt_still_restores(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)

    class Boom(FakeApi):
        def post(self, *a):
            raise KeyboardInterrupt
    h = Harness(stubbed, tmp_path, api_obj=Boom())
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.expect_dispatch_flip(True, 13, 14)
    with pytest.raises(KeyboardInterrupt):
        h.run(path, plan)
    assert not breadcrumb(tmp_path).exists() and h.tunnel_closed == 1


def test_restore_failure_keeps_breadcrumb(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.expect_puts(1)
    h.ac.err("create_hosted_configuration_version", "ConflictException", ApplicationId="app",
             ConfigurationProfileId="prof", Content=dispatch.build_content(deployed(), True),
             ContentType="application/json")
    out = h.run(path, plan)
    assert out.exit_code == 3 and out.report["restore_failed"] is True
    assert breadcrumb(tmp_path).exists()


def test_already_closed_and_stays_closed_makes_no_appconfig_writes(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, was_enabled=False, restore_to=False, claims_n=1)
    h = Harness(stubbed, tmp_path, enabled=False)
    h.expect_latest_deployment_time()
    h.expect_off()
    h.expect_puts(1)
    out = h.run(path, plan)
    assert out.exit_code == 0 and h.sleeps == []
    assert out.report["opened_dispatch"] is False


def test_closed_then_opened_reports_opened(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, was_enabled=False, restore_to=True, claims_n=1)
    h = Harness(stubbed, tmp_path, enabled=False)
    h.expect_strategy()
    h.expect_latest_deployment_time()
    h.expect_off()
    h.expect_puts(1)
    h.expect_dispatch_flip(True, 13, 14)
    out = h.run(path, plan)
    assert out.exit_code == 0 and out.report["opened_dispatch"] is True
    assert out.report["dispatch"] == {"before": False, "after": True, "restore_to": True}


def drain(h):
    h.sts.stub._queue.clear()


def test_plan_id_mismatch_aborts_before_any_aws_call(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path)
    drain(h)
    out = launcher.execute_plan(path, "deadbeef0000", h.deps, settle_seconds=75)
    assert out.exit_code == 1 and "plan_id" in out.report["abort"]
    assert h.tunnel_opened == 0


def test_tampered_plan_aborts(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    data = json.loads(path.read_text())
    data["claims"][0]["body"]["idReclamacion"] = 1
    path.write_text(json.dumps(data))
    h = Harness(stubbed, tmp_path)
    drain(h)
    out = launcher.execute_plan(path, plan["plan_id"], h.deps, settle_seconds=75)
    assert out.exit_code == 1


def test_wrong_account_aborts(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, account="999999999999")
    out = h.run(path, plan)
    assert out.exit_code == 1 and "999999999999" in out.report["abort"] and h.tunnel_opened == 0


def test_sensitive_profile_aborts(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, mutate=lambda p: p.update(profile="ADR-" + "PROD" + "-X"))
    h = Harness(stubbed, tmp_path)
    drain(h)
    out = h.run(path, plan)
    assert out.exit_code == 1 and "sensible" in out.report["abort"]


def test_unsupported_env_aborts(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, mutate=lambda p: p.update(env="other"))
    h = Harness(stubbed, tmp_path)
    drain(h)
    assert h.run(path, plan).exit_code == 1


def test_config_drift_aborts_before_pause(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path,
                live=live_paths(versions={"api/storage": 7, "throttle-controller/dispatch": 9}))
    out = h.run(path, plan)
    assert out.exit_code == 1 and "config cambió desde el plan" in out.report["abort"]
    assert "api/storage" in out.report["abort"] and h.tunnel_opened == 0


def test_deployment_in_progress_aborts(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, live=live_paths(in_progress={"api/storage": (5,)}))
    assert h.run(path, plan).exit_code == 1


def test_missing_secret_aborts_before_pause_and_prints_command(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, secret=None)
    out = h.run(path, plan)
    assert out.exit_code == 1 and "asm-exec" in out.report["abort"] and h.tunnel_opened == 0
    assert not breadcrumb(tmp_path).exists()


def test_bad_audience_aborts_before_pause(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, token=auth.Token(jwt({"aud": "account"})))
    out = h.run(path, plan)
    assert out.exit_code == 1 and "aud" in out.report["abort"] and h.tunnel_opened == 0


def test_probe_not_404_aborts_before_pause(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path, api_obj=FakeApi(probe=403))
    out = h.run(path, plan)
    assert out.exit_code == 1 and "403" in out.report["abort"]
    assert h.tunnel_closed == 1 and not breadcrumb(tmp_path).exists()


def test_no_strategy_aborts_before_pause(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path)
    h.ac.ok("list_deployment_strategies", {"Items": []})
    out = h.run(path, plan)
    assert out.exit_code == 1 and "estrategia" in out.report["abort"]


def test_settle_below_61_rejected(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path)
    drain(h)
    with pytest.raises(ValueError, match="61"):
        h.run(path, plan, settle_seconds=30)


def test_token_refreshed_after_240s(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=2)
    h = Harness(stubbed, tmp_path, token=auth.Token(jwt({"aud": envs.expected_audience("dev")})))  # sin exp
    t = {"now": 0.0}
    h.deps.clock = lambda: t["now"]
    h.deps.sleep = lambda s: t.__setitem__("now", t["now"] + 300)  # el asentamiento (75 s) "tarda" 300 s
    happy_expectations(h)
    h.run(path, plan)
    assert h.token_calls >= 2


def test_recover_restores_and_deletes(stubbed, tmp_path, monkeypatch):
    monkeypatch.setattr(dispatch, "pid_alive", lambda pid: False)
    dispatch.write_breadcrumb("dev", tmp_path / "state", app="a", was_enabled=True, restore_to=True,
                              run_id="r", pid=1)
    h = Harness(stubbed, tmp_path, enabled=False)
    h.expect_strategy()
    h.expect_dispatch_flip(True, 13, 14)
    drain(h)  # recover no necesita sts? se vuelve a encolar abajo
    h.sts.ok("get_caller_identity", {"Account": ACCOUNT, "Arn": "arn:aws:iam::123456789012:user/x",
                                      "UserId": "u"})
    out = launcher.recover("dev", h.deps, execute=True)
    assert out.exit_code == 0 and not breadcrumb(tmp_path).exists()


def test_recover_without_execute_only_describes(stubbed, tmp_path):
    dispatch.write_breadcrumb("dev", tmp_path / "state", app="a", was_enabled=True, restore_to=True,
                              run_id="r", pid=1)
    h = Harness(stubbed, tmp_path, enabled=False)
    drain(h)
    out = launcher.recover("dev", h.deps, execute=False)
    assert out.exit_code == 0 and breadcrumb(tmp_path).exists() and "restore_to" in json.dumps(out.report)


def test_recover_nothing_to_do(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path)
    drain(h)
    assert launcher.recover("dev", h.deps, execute=True).report["recover"] == "sin miga de pausa"


def test_describe_lists_actions(tmp_path):
    path, plan = make_plan(tmp_path)
    text = launcher.describe(path)
    assert plan["plan_id"] in text and "0_100" in text and "asm-exec" in text and "POST" in text
