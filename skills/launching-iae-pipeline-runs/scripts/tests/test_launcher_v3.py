"""Ronda de correcciones: H1/H2, M1-M6, L2/L4/L8."""
import json
from datetime import datetime, timezone

from botocore.stub import ANY

from iae_launch import api, auth, dispatch, envs, launcher
from iae_launch.live import Deployed
from tests.test_checks_env import jwt
from tests.test_launcher import (
    BUCKET,
    DISPATCH_DOC,
    FakeApi,
    Harness,
    breadcrumb,
    deployed,
    drain,
    happy_expectations,
    make_plan,
)

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def aborted(out, text):
    assert out.exit_code == 1 and text in out.report["abort"], out.report


# ---- H1: no relanzar sobre una corrida ya ejecutada ---------------------------------------
def test_refuses_when_launch_report_exists(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    (path.parent / "launch_report.json").write_text("{}")
    h = Harness(stubbed, tmp_path)
    aborted(h.run(path, plan), "ya tiene launch_report.json")
    assert h.tunnel_opened == 0


def test_refuses_when_index_already_has_pids(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    (path.parent / "process_index.csv").write_text(
        "radicado,pid,descargado,s3uri\n0_100,pidX,false,s3://x/\n")
    h = Harness(stubbed, tmp_path)
    aborted(h.run(path, plan), "0_100")


def test_refuses_malformed_index(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    (path.parent / "process_index.csv").write_text("a,b\n1,2\n")
    aborted(Harness(stubbed, tmp_path).run(path, plan), "cabecera")


def test_refuses_when_a_breadcrumb_exists_even_the_runners(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    crumb = tmp_path / "state" / "pipeline-runner" / "paused-dev.json"
    crumb.parent.mkdir(parents=True)
    crumb.write_text("{}")
    h = Harness(stubbed, tmp_path)
    aborted(h.run(path, plan), "miga de pausa")
    assert h.tunnel_opened == 0


def test_errors_after_first_write_are_not_reported_as_abort(stubbed, tmp_path, monkeypatch):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    happy_expectations(h, 1)

    def boom(*a, **k):
        raise OSError("disco lleno")
    monkeypatch.setattr(launcher.Path, "write_text", boom)  # el reporte no se puede escribir
    out = h.run(path, plan)
    assert "abort" not in out.report and "launch_report.json" in out.report["error"]
    assert out.exit_code == 0 or out.exit_code == 3


def test_crumb_delete_failure_is_reported_not_raised(stubbed, tmp_path, monkeypatch):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    happy_expectations(h, 1)

    def boom(env, home):
        raise PermissionError("denegado")
    monkeypatch.setattr(dispatch, "delete_breadcrumb", boom)
    out = h.run(path, plan)
    assert out.report["crumb_delete_failed"] is True and "abort" not in out.report


# ---- H2: restaurar con documento fresco, reintentos --------------------------------------
def test_restore_uses_fresh_dispatch_document_not_the_start_snapshot(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    edited = json.loads(json.dumps(DISPATCH_DOC))
    edited["values"]["dispatch"]["maxMessagesPerCycle"] = 99          # alguien lo editó durante la corrida
    reads = {"n": 0}

    def reload():
        reads["n"] += 1
        d = deployed(reads["n"] > 1)   # 1.ª lectura (pausa): abierto; 2.ª (restauración): editado
        return Deployed(d.app_id, d.env_id, d.profile_id, d.version, d.deployment_number,
                        edited if reads["n"] > 1 else d.content)
    h.deps.reload_dispatch = reload
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.expect_puts(1)
    restore = Deployed("app", "env", "prof", 9, 1, edited)
    h.ac.ok("create_hosted_configuration_version", {"VersionNumber": 13, "ContentType": "application/json"},
            ApplicationId="app", ConfigurationProfileId="prof", Content=dispatch.build_content(restore, True),
            ContentType="application/json")
    h.ac.ok("start_deployment", {"DeploymentNumber": 14}, ApplicationId="app", EnvironmentId="env",
            DeploymentStrategyId="strat", ConfigurationProfileId="prof", ConfigurationVersion="13")
    h.ac.ok("get_deployment", {"State": "COMPLETE"}, ApplicationId="app", EnvironmentId="env", DeploymentNumber=14)
    out = h.run(path, plan)
    assert out.exit_code == 0 and reads["n"] == 2


def test_restore_retries_on_conflict(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.expect_puts(1)
    h.ac.err("create_hosted_configuration_version", "ConflictException", ApplicationId="app",
             ConfigurationProfileId="prof", Content=dispatch.build_content(deployed(), True),
             ContentType="application/json")
    h.expect_dispatch_flip(True, 13, 14)
    out = h.run(path, plan)
    assert out.exit_code == 0 and out.report["dispatch"]["after"] is True
    assert dispatch.RETRY_BACKOFF in h.sleeps


# ---- L2: el OFF debe ser posterior al fin del deployment de pausa ----------------------------
def test_off_must_follow_pause_deployment_completion(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    done = datetime(2026, 11, 9, 12, 0, 42, tzinfo=timezone.utc)
    h.expect_strategy()
    d = deployed(True)
    h.ac.ok("create_hosted_configuration_version", {"VersionNumber": 11, "ContentType": "application/json"},
            ApplicationId="app", ConfigurationProfileId="prof", Content=dispatch.build_content(d, False),
            ContentType="application/json")
    h.ac.ok("start_deployment", {"DeploymentNumber": 12}, ApplicationId="app", EnvironmentId="env",
            DeploymentStrategyId="strat", ConfigurationProfileId="prof", ConfigurationVersion="11")
    h.ac.ok("get_deployment", {"State": "COMPLETE", "CompletedAt": done}, ApplicationId="app",
            EnvironmentId="env", DeploymentNumber=12)
    h.expect_off(int(done.timestamp() * 1000))
    h.expect_puts(1)
    h.expect_dispatch_flip(True, 13, 14)
    assert h.run(path, plan).exit_code == 0


# ---- M1: procedencia del plan ------------------------------------------------------------------
def test_plan_with_foreign_bucket_is_refused(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, mutate=lambda p: p["live"].update(workarea_bucket="otro-bucket"))
    h = Harness(stubbed, tmp_path)
    aborted(h.run(path, plan), "workarea")


def test_plan_with_other_api_host_is_refused(stubbed, tmp_path):
    path, plan = make_plan(tmp_path)
    h = Harness(stubbed, tmp_path)
    h.deps.api_url = lambda: "https://zzz.execute-api.us-east-1.amazonaws.com/v1"
    aborted(h.run(path, plan), "API")


def test_put_source_outside_plan_dirs_is_refused(stubbed, tmp_path):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    secret = outside / "id_rsa"
    secret.write_text("x")

    def mutate(p):
        p["claims"][0]["seed_items"][0].update(source=str(secret), size=1)
    path, plan = make_plan(tmp_path, mutate=mutate)
    aborted(Harness(stubbed, tmp_path).run(path, plan), "fuera de las carpetas")


def test_copy_source_outside_workarea_is_refused(stubbed, tmp_path):
    def mutate(p):
        p["claims"][0]["seed_items"][1]["source"] = "s3://bucket-ajeno/audit-processes/x/k.json"
    path, plan = make_plan(tmp_path, mutate=mutate)
    aborted(Harness(stubbed, tmp_path).run(path, plan), "workarea/MAI")


def test_copy_source_with_wrong_prefix_is_refused(stubbed, tmp_path):
    def mutate(p):
        p["claims"][0]["seed_items"][1]["source"] = f"s3://{BUCKET}/otro-prefijo/k.json"
    path, plan = make_plan(tmp_path, mutate=mutate)
    aborted(Harness(stubbed, tmp_path).run(path, plan), "workarea/MAI")


def test_mai_copy_source_is_allowed(stubbed, tmp_path):
    def mutate(p):
        p["claims"][0]["seed_items"][1]["source"] = (
            "s3://adr-medical-audit-executions-local-mai/runs/r1/f/200_soportes_estructurados/a.json")
    path, plan = make_plan(tmp_path, claims_n=1, mutate=mutate)
    h = Harness(stubbed, tmp_path)
    h.sts.stub._queue.clear()
    h.sts.ok("get_caller_identity", {"Account": "072055531089", "Arn": "arn:aws:iam::123456789012:user/x",
                                      "UserId": "u"})
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.s3.ok("put_object", {}, Bucket=BUCKET, Key=ANY, Body=ANY, ContentType="application/pdf")
    h.s3.ok("copy_object", {}, Bucket=BUCKET, Key=ANY, CopySource={
        "Bucket": "adr-medical-audit-executions-local-mai",
        "Key": "runs/r1/f/200_soportes_estructurados/a.json"},
        ContentType="application/json", MetadataDirective="REPLACE")
    h.expect_dispatch_flip(True, 13, 14)
    assert h.run(path, plan).exit_code == 0


def test_dest_suffix_traversal_refused(stubbed, tmp_path):
    def mutate(p):
        p["claims"][0]["seed_items"][0]["dest_suffix"] = "../../evil"
    path, plan = make_plan(tmp_path, mutate=mutate)
    aborted(Harness(stubbed, tmp_path).run(path, plan), "destino")


def test_base_prefix_mismatch_with_live_refused(stubbed, tmp_path):
    def mutate(p):
        p["live"]["base_prefix"] = "otro"
        p["claims"][0]["seed_items"][1]["source"] = f"s3://{BUCKET}/otro/x/k.json"  # coherente con el plan
    path, plan = make_plan(tmp_path, claims_n=1, mutate=mutate)
    aborted(Harness(stubbed, tmp_path).run(path, plan), "base_prefix")


# ---- M2 / L4 -------------------------------------------------------------------------------------
def test_recibido_with_bad_pid_is_bad_response(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    bad = api.IniciarResult(False, "basura", "RECIBIDO", "idProcessIA inválido", bad_response=True)
    h = Harness(stubbed, tmp_path, api_obj=FakeApi([bad]))
    happy_expectations(h, 0)
    out = h.run(path, plan)
    assert out.report["failures"][0]["status"] == "bad_response" and "tracker" in out.report["failures"][0]["detail"]


def test_transport_error_tells_to_check_tracker(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path, api_obj=FakeApi([TimeoutError("timed out")]))
    happy_expectations(h, 0)
    detail = h.run(path, plan).report["failures"][0]["detail"]
    assert "TimeoutError" in detail and "tracker" in detail


def test_http_error_does_not_suggest_tracker(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path, api_obj=FakeApi([api.ApiError(400, "bad")]))
    happy_expectations(h, 0)
    assert "tracker" not in h.run(path, plan).report["failures"][0]["detail"]


# ---- M4 -----------------------------------------------------------------------------------------------
def test_recover_and_open_refuse_while_owner_alive(stubbed, tmp_path, monkeypatch):
    dispatch.write_breadcrumb("dev", tmp_path / "state", app="a", was_enabled=True, restore_to=True,
                              run_id="r", pid=4242)
    monkeypatch.setattr(dispatch, "pid_alive", lambda pid: True)
    h = Harness(stubbed, tmp_path, enabled=False)
    drain(h)
    assert "4242" in launcher.recover("dev", h.deps, execute=True).report["abort"]
    assert "4242" in launcher.open_dispatch("dev", h.deps, execute=True).report["abort"]
    assert breadcrumb(tmp_path).exists()


# ---- M5 -------------------------------------------------------------------------------------------------
def test_deps_and_holder_repr_hide_secret(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path, secret="hunter2-secret")
    holder = launcher._TokenHolder(h.deps, envs.get_env("dev"))
    assert "hunter2" not in repr(h.deps) and "hunter2" not in repr(holder)
    assert "eyJ" not in repr(holder)
    h.sts.stub._queue.clear()


# ---- M6 ---------------------------------------------------------------------------------------------------
def test_leave_closed_with_incomplete_pause_keeps_crumb_and_reports_unknown(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    h.expect_strategy()
    h.ac.err("create_hosted_configuration_version", "InternalServerException", ApplicationId="app",
             ConfigurationProfileId="prof", Content=dispatch.build_content(deployed(), False),
             ContentType="application/json")
    out = h.run(path, plan, leave_closed=True)
    assert out.report["pause_incomplete"] is True and out.report["dispatch"]["after"] is None
    assert breadcrumb(tmp_path).exists() and out.exit_code == 1


# ---- L8 -------------------------------------------------------------------------------------------------------
def test_token_refreshes_based_on_exp(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path)
    now_ts = int(NOW.timestamp())
    calls = []

    def token_fn(spec, secret):
        calls.append(1)
        return auth.Token(jwt({"aud": envs.expected_audience("dev"), "exp": now_ts + (30 if len(calls) == 1 else 3600)}))
    h.deps.token_fn = token_fn
    holder = launcher._TokenHolder(h.deps, envs.get_env("dev"))
    holder.fresh()           # exp en 30 s < margen: renueva
    assert len(calls) == 2
    holder.fresh()           # exp en 1 h: no renueva
    assert len(calls) == 2
    h.sts.stub._queue.clear()


# ---- stop_run: una falla no impide detener las demás ----------------------------------------------------
def test_stop_run_continues_after_a_stop_failure(stubbed, tmp_path):
    from tests.test_launcher_v2 import SM, execution, run_dir, stop_harness, tracker_get
    run = run_dir(tmp_path)
    h = stop_harness(stubbed, tmp_path)
    a, b = execution("pidA-1"), execution("pidB-1")
    h.sf.ok("list_executions", {"executions": [a, b]}, stateMachineArn=SM, statusFilter="RUNNING")
    h.sf.err("stop_execution", "ExecutionDoesNotExist", executionArn=a["executionArn"], error="Relaunch", cause="x")
    h.sf.ok("stop_execution", {"stopDate": NOW}, executionArn=b["executionArn"], error="Relaunch", cause="x")
    tracker_get(h.ddb, "pidA", "SF_ABORTED")
    tracker_get(h.ddb, "pidB", "SF_ABORTED")
    out = launcher.stop_run(run, h.deps, execute=True, cause="x")
    assert out.exit_code == 3 and out.report["stopped"] == ["pidB"] and "pidA" in out.report["stop_errors"]
