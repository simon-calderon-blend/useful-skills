import json

import pytest

from iae_launch import auth, checks, cli, jumphost, launcher, runner
from tests.test_launcher import make_plan
from tests.test_plan import FIELDS, inputs, make_claim, result

SENSITIVE = "ADR-" + "PROD" + "-X"


@pytest.mark.parametrize("main", [cli.main_preflight, cli.main_prepare, cli.main_launch, cli.main_monitor])
def test_unsupported_env_rejected_by_argparse(main):
    with pytest.raises(SystemExit) as ei:
        main(["--env", "prod"])
    assert ei.value.code == 2


def test_preflight_sensitive_profile_prints_failed_json(capsys):
    code = cli.main_preflight(["--env", "dev", "--profile", SENSITIVE])
    out = json.loads(capsys.readouterr().out)
    assert code == 1 and out["ok"] is False and out["checks"][0]["name"] == "profile_not_sensitive"


def test_preflight_exit_codes(monkeypatch, capsys):
    ok = runner.PreflightResult(checks.Report([checks.Check("a", "ok", "d", "p")]), runner.Resolved(), {})
    monkeypatch.setattr(cli, "_preflight", lambda a, run_id: (runner.Inputs(env="dev", profile="p"), None, ok))
    monkeypatch.delenv("IAE_CLIENT_SECRET", raising=False)
    assert cli.main_preflight(["--env", "dev"]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_prepare_refuses_skip_preflight(capsys):
    assert cli.main_prepare(["--env", "dev", "--skip-preflight", "--structuring", "none", "--request", "api", "--invoice", "local"]) == 2


def test_prepare_requires_claims():
    with pytest.raises(SystemExit) as ei:
        cli.main_prepare(["--env", "dev", "--structuring", "none", "--request", "api", "--invoice", "local"])
    assert ei.value.code == 2


def test_prepare_failed_preflight_exits_1(monkeypatch, tmp_path, capsys):
    bad = runner.PreflightResult(checks.Report([checks.Check("a", "FAILED", "d", "p")]), runner.Resolved(), {})
    monkeypatch.setattr(cli, "_preflight", lambda a, run_id: (None, None, bad))
    code = cli.main_prepare(["--env", "dev", "--source-dir", str(tmp_path), "--claim", "x", "--structuring", "none", "--request", "api", "--invoice", "local"])
    assert code == 1 and '"FAILED"' in capsys.readouterr().out


def test_prepare_writes_plan_and_prints_command(monkeypatch, tmp_path, capsys, stubbed):
    src = tmp_path / "src"
    make_claim(src, "1_100", {"FAC_1.pdf": "x", "claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    res = result(FIELDS)
    res = runner.PreflightResult(checks.Report([checks.Check("a", "ok", "d", "p")]), res.resolved, FIELDS)
    inp = inputs(src, ["1_100"])
    inp = runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_dir=src, claims=["1_100"])
    ac = stubbed("appconfig")
    ac.ok("list_deployments", {"Items": []}, ApplicationId="a", EnvironmentId="e")
    clients = runner.Clients(appconfig=ac.client, s3=object())
    monkeypatch.setattr(cli, "_preflight", lambda a, run_id: (inp, clients, res))
    out_dir = tmp_path / "runs"
    code = cli.main_prepare(["--env", "dev", "--source-dir", str(src), "--claim", "1_100", "--structuring", "none", "--request", "api", "--invoice", "local",
                             "--run-id", "skill-x", "--out-dir", str(out_dir)])
    text = capsys.readouterr().out
    assert code == 0 and "asm-exec" in text and (out_dir / "skill-x" / "plan.json").exists()


def test_launch_without_execute_only_describes(tmp_path, capsys):
    path, plan = make_plan(tmp_path)
    assert cli.main_launch(["--env", "dev", "--plan", str(path)]) == 0
    assert plan["plan_id"] in capsys.readouterr().out


def test_launch_execute_requires_plan_id(tmp_path):
    path, _ = make_plan(tmp_path)
    with pytest.raises(SystemExit) as ei:
        cli.main_launch(["--env", "dev", "--plan", str(path), "--execute"])
    assert ei.value.code == 2


def test_launch_requires_plan_or_recover():
    with pytest.raises(SystemExit):
        cli.main_launch(["--env", "dev"])


def test_launch_sensitive_profile_refused(capsys):
    assert cli.main_launch(["--env", "dev", "--profile", SENSITIVE, "--plan", "x"]) == 1


def test_launch_execute_delegates(monkeypatch, tmp_path, capsys):
    path, plan = make_plan(tmp_path)
    seen = {}

    def fake_execute(p, pid, deps, settle_seconds, leave_closed):
        seen.update(p=p, pid=pid, settle=settle_seconds, leave=leave_closed)
        return launcher.Outcome(3, {"x": 1})
    monkeypatch.setattr(cli, "_launch_deps", lambda env, profile: "deps")
    monkeypatch.setattr(launcher, "execute_plan", fake_execute)
    monkeypatch.setattr(cli.signal, "signal", lambda *a: None)
    code = cli.main_launch(["--env", "dev", "--plan", str(path), "--execute", "--plan-id", plan["plan_id"],
                            "--pause-settle-seconds", "90", "--leave-dispatch-closed"])
    assert code == 3 and seen == {"p": path, "pid": plan["plan_id"], "settle": 90, "leave": True}


def test_launch_recover_delegates(monkeypatch, capsys):
    monkeypatch.setattr(cli, "_launch_deps", lambda env, profile: "deps")
    monkeypatch.setattr(launcher, "recover", lambda env, deps, execute: launcher.Outcome(0, {"recover": "ok"}))
    assert cli.main_launch(["--env", "test", "--recover"]) == 0
    assert "recover" in capsys.readouterr().out


def test_launch_deps_wiring(monkeypatch):
    class Sess:
        def client(self, name, region_name=None):
            return object()
    monkeypatch.setattr(cli, "make_session", lambda profile: Sess())
    deps = cli._launch_deps("dev", "ADR-DEV-MEDICALAUDIT")
    assert deps.token_fn is auth.get_token and callable(deps.open_tunnel) and callable(deps.gather)


def test_launch_deps_open_tunnel_uses_bastion(monkeypatch):
    class Sess:
        def client(self, name, region_name=None):
            return "ssm-client"
    seen = {}
    monkeypatch.setattr(cli, "make_session", lambda profile: Sess())
    monkeypatch.setattr(cli.tunnel, "open_tunnel", lambda **kw: seen.update(kw) or "cm")
    monkeypatch.setattr(cli.jumphost, "resolve", lambda ssm, ec2, spec: jumphost.JumpHost("i-live", "b", "x"))
    deps = cli._launch_deps("dev", "ADR-DEV-MEDICALAUDIT")
    assert deps.open_tunnel("host.example") == "cm"
    assert seen["bastion"] == "i-live" and seen["host"] == "host.example"
    assert seen["ssm"] == "ssm-client"


def test_probe_factory_opens_tunnel_and_probes(monkeypatch):
    from contextlib import contextmanager

    from iae_launch import envs

    @contextmanager
    def fake_open(**kw):
        yield type("T", (), {"connection_factory": staticmethod(lambda *a: None)})()
    monkeypatch.setattr(cli.tunnel, "open_tunnel", fake_open)
    monkeypatch.setattr(cli.api, "probe_proceso", lambda f, base, tok, pid: 404)
    resolved = runner.Resolved(api_base_url="https://abc.execute-api.us-east-1.amazonaws.com/v1")
    probe = cli._probe_factory(envs.get_env("dev"), runner.Clients(ssm=object()))(resolved, auth.Token("t"))
    assert probe() == 404


def test_monitor_delegates(monkeypatch, tmp_path, capsys):
    class Sess:
        def client(self, name, region_name=None):
            return object()
    seen = {}
    monkeypatch.setattr(cli, "make_session", lambda profile: Sess())
    monkeypatch.setattr(cli.monitor, "run_monitor", lambda run_dir, clients, **kw: seen.update(kw) or {"ok": 1})
    code = cli.main_monitor(["--env", "test", "--run-dir", str(tmp_path), "--once", "--download",
                             "--close-dispatch-when-done", "yes", "--execute"])
    assert code == 0 and seen["once"] and seen["download"] and seen["close_mode"] == "yes" and seen["execute"]
    seen["gather"]  # callable


def test_monitor_sensitive_profile_refused(tmp_path):
    assert cli.main_monitor(["--env", "dev", "--profile", SENSITIVE, "--run-dir", str(tmp_path)]) == 1


def test_launch_open_dispatch_and_stop_run_delegate(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli, "_launch_deps", lambda env, profile: "deps")
    seen = {}
    monkeypatch.setattr(launcher, "open_dispatch",
                        lambda env, deps, execute: seen.update(open=execute) or launcher.Outcome(0, {"o": 1}))
    monkeypatch.setattr(launcher, "stop_run", lambda run, deps, execute, cause: seen.update(stop=(run, execute, cause))
                        or launcher.Outcome(3, {"s": 1}))
    assert cli.main_launch(["--env", "dev", "--open-dispatch", "--execute"]) == 0
    assert cli.main_launch(["--env", "dev", "--stop-run", str(tmp_path), "--execute", "--stop-cause", "c"]) == 3
    assert seen == {"open": True, "stop": (tmp_path, True, "c")}


def test_source_index_defaults_and_exclusivity():
    import argparse
    p = argparse.ArgumentParser()
    cli._env_arg(p)
    cli._claim_args(p)
    a = p.parse_args(["--env", "test", "--source-index", "i.csv"])
    inp = cli._inputs(a)
    assert (inp.structuring, inp.request, inp.invoice) == ("workarea", "source", "lambda")
    b = p.parse_args(["--env", "test", "--source-dir", "d", "--claim", "x"])
    inp = cli._inputs(b)
    assert (inp.structuring, inp.request, inp.invoice) == ("none", "api", "local")
    with pytest.raises(SystemExit):
        p.parse_args(["--env", "test", "--source-dir", "d", "--source-index", "i.csv"])


def test_incoherent_arguments_exit_2():
    with pytest.raises(SystemExit) as ei:
        cli.main_preflight(["--env", "test", "--source-index", "i.csv", "--invoice", "ser"])
    assert ei.value.code == 2


def test_launch_dry_run_missing_plan_is_clean_error(tmp_path, capsys):
    assert cli.main_launch(["--env", "dev", "--plan", str(tmp_path / "nope.json")]) == 1
    assert "plan inválido" in capsys.readouterr().err


@pytest.mark.parametrize("missing", ["--structuring", "--request", "--invoice"])
def test_prepare_requires_every_decision(missing):
    args = {"--structuring": "none", "--request": "api", "--invoice": "local"}
    del args[missing]
    argv = ["--env", "dev", "--source-dir", "d", "--claim", "x"] + [t for kv in args.items() for t in kv]
    with pytest.raises(SystemExit) as ei:
        cli.main_prepare(argv)
    assert ei.value.code == 2


def test_prepare_source_index_also_requires_decisions():
    with pytest.raises(SystemExit) as ei:
        cli.main_prepare(["--env", "test", "--source-index", "i.csv"])
    assert ei.value.code == 2


def test_request_value_validation():
    assert cli._request_value("source:11111111-1111-4111-8111-111111111111")
    for bad in ("source:x", "bogus", "SOURCE"):
        with pytest.raises(cli.argparse.ArgumentTypeError):
            cli._request_value(bad)


def test_preflight_lists_missing_decisions_and_secret_hint(monkeypatch, capsys):
    ok = runner.PreflightResult(checks.Report([checks.Check("a", "ok", "d", "p")]), runner.Resolved(),
                                {"1_100": {"idReclamacion": 100, "idSolicitud": 100}})
    inp = runner.Inputs(env="dev", profile="p", source_dir="d", claims=["1_100"], name_template="<ignore>_<numero>")
    monkeypatch.setattr(cli, "_preflight", lambda a, run_id: (inp, None, ok))
    monkeypatch.delenv("IAE_CLIENT_SECRET", raising=False)
    cli.main_preflight(["--env", "dev", "--request", "api"])
    out = json.loads(capsys.readouterr().out)["summary"]
    assert "--structuring" in out["missing_decisions"] and "--invoice" in out["missing_decisions"]
    assert "--request" not in out["missing_decisions"]
    assert out["token_checks"].startswith("token/aud/api checks skipped — rerun under: env AWS_PROFILE=")
    assert "asm-exec" in out["token_checks"] and "preflight.py --env dev --request api" in out["token_checks"]
    assert out["claims_parsed"] == {"1_100": {"idReclamacion": 100, "idSolicitud": 100}}
    assert out["name_pattern"]["template"] == "<ignore>_<numero>"


def test_preflight_no_hint_when_secret_present(monkeypatch, capsys):
    ok = runner.PreflightResult(checks.Report([]), runner.Resolved(), {})
    monkeypatch.setattr(cli, "_preflight", lambda a, run_id: (runner.Inputs(env="dev", profile="p"), None, ok))
    monkeypatch.setenv("IAE_CLIENT_SECRET", "x")
    cli.main_preflight(["--env", "dev", "--structuring", "none", "--request", "api", "--invoice", "local"])
    out = json.loads(capsys.readouterr().out)["summary"]
    assert "token_checks" not in out and "missing_decisions" not in out


def test_index_summary_shows_request_source_pid():
    from tests.test_source_mode import source
    sc = source()
    sc.request_pid = "22222222-2222-4222-8222-222222222222"
    sc.inspected = [("00000000-0000-4000-8000-000000000001", "sin request.json en S3")]
    res = runner.PreflightResult(None, runner.Resolved(), {})
    res.sources = {"0001_5": sc}
    out = cli._claims_summary(runner.Inputs(env="test", profile="p", source_index="i.csv"), res)
    assert out["request_source_pid"] == {"0001_5": sc.request_pid}
    assert "sin request.json" in out["request_pids_descartados"]["0001_5"][0]


@pytest.mark.parametrize("flags", [["--recover", "--open-dispatch"], ["--plan", "p", "--recover"],
                                   ["--stop-run", "d", "--open-dispatch"], ["--plan", "p", "--stop-run", "d"]])
def test_launch_modes_are_mutually_exclusive(flags):
    with pytest.raises(SystemExit) as ei:
        cli.main_launch(["--env", "dev", *flags])
    assert ei.value.code == 2


def test_launch_traps_sighup_like_sigterm(monkeypatch, tmp_path):
    path, plan = make_plan(tmp_path)
    trapped = []
    monkeypatch.setattr(cli, "_launch_deps", lambda env, profile: "deps")
    monkeypatch.setattr(launcher, "execute_plan", lambda *a, **k: launcher.Outcome(0, {}))
    monkeypatch.setattr(cli.signal, "signal", lambda sig, handler: trapped.append(sig))
    cli.main_launch(["--env", "dev", "--plan", str(path), "--execute", "--plan-id", plan["plan_id"]])
    assert set(trapped) == {cli.signal.SIGTERM, cli.signal.SIGHUP}


def test_monitor_exit_code_on_dispatch_error(monkeypatch, tmp_path, capsys):
    class Sess:
        def client(self, name, region_name=None):
            return object()
    monkeypatch.setattr(cli, "make_session", lambda profile: Sess())
    monkeypatch.setattr(cli.monitor, "run_monitor", lambda *a, **k: {"dispatch_error": True})
    assert cli.main_monitor(["--env", "test", "--run-dir", str(tmp_path)]) == 1
    assert "dispatch_error" in capsys.readouterr().out
