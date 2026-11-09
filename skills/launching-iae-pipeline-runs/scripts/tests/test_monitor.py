import json
from datetime import datetime, timedelta, timezone

import pytest

from iae_launch import dispatch, monitor, runner
from iae_launch.live import Deployed, LivePaths
from tests.conftest import stream

SM = "arn:aws:states:us-east-1:072055531089:stateMachine:adr-dev-medicalaudit-pipeline"
START = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def ex(name, status, start, arn=None):
    return {"executionArn": arn or f"{SM.replace('stateMachine', 'execution')}:{name}", "stateMachineArn": SM,
            "name": name, "status": status, "startDate": start}


def tracked():
    return {"0_100": monitor.Tracked("0_100", "pidA"), "1_101": monitor.Tracked("1_101", "pidB")}


def test_poll_maps_names_and_describes_running(stubbed):
    sf = stubbed("stepfunctions")
    a, b = ex("pidA-1", "RUNNING", START + timedelta(minutes=1)), ex("pidB-1", "SUCCEEDED", START + timedelta(minutes=2))
    other = ex("zzz-9", "RUNNING", START + timedelta(minutes=3))
    sf.ok("list_executions", {"executions": [other, b, a]}, stateMachineArn=SM)
    sf.ok("describe_execution", {"executionArn": a["executionArn"], "stateMachineArn": SM, "name": "pidA-1",
                                 "status": "RUNNING", "startDate": a["startDate"], "input": "{}"},
          executionArn=a["executionArn"])
    t = tracked()
    monitor.poll_once(sf.client, SM, t, START, sleep=lambda s: None)
    assert t["0_100"].status == "RUNNING" and t["1_101"].status == "SUCCEEDED"
    assert t["1_101"].execution_arn == b["executionArn"]


def test_poll_stops_paging_before_run_start(stubbed):
    sf = stubbed("stepfunctions")
    new = ex("pidA-1", "SUCCEEDED", START + timedelta(minutes=1))
    old = ex("old-1", "SUCCEEDED", START - timedelta(minutes=30))
    sf.ok("list_executions", {"executions": [new, old], "nextToken": "n"}, stateMachineArn=SM)
    t = {"0_100": monitor.Tracked("0_100", "pidA")}
    monitor.poll_once(sf.client, SM, t, START, sleep=lambda s: None)  # no pide la 2ª página
    assert t["0_100"].status == "SUCCEEDED"


def test_poll_follows_next_token(stubbed):
    sf = stubbed("stepfunctions")
    sf.ok("list_executions", {"executions": [ex("x-1", "RUNNING", START + timedelta(minutes=5))],
                              "nextToken": "n"}, stateMachineArn=SM)
    sf.ok("list_executions", {"executions": [ex("pidA-1", "FAILED", START + timedelta(minutes=1))]},
          stateMachineArn=SM, nextToken="n")
    t = {"0_100": monitor.Tracked("0_100", "pidA")}
    monitor.poll_once(sf.client, SM, t, START, sleep=lambda s: None)
    assert t["0_100"].status == "FAILED"


def test_not_started_when_no_execution(stubbed):
    sf = stubbed("stepfunctions")
    sf.ok("list_executions", {"executions": []}, stateMachineArn=SM)
    t = {"0_100": monitor.Tracked("0_100", "pidA")}
    monitor.poll_once(sf.client, SM, t, START, sleep=lambda s: None)
    assert t["0_100"].status == "not_started"


def test_throttling_backs_off_then_succeeds(stubbed):
    sf = stubbed("stepfunctions")
    sf.err("list_executions", "ThrottlingException", stateMachineArn=SM)
    sf.err("list_executions", "ThrottlingException", stateMachineArn=SM)
    sf.ok("list_executions", {"executions": [ex("pidA-1", "SUCCEEDED", START + timedelta(minutes=1))]},
          stateMachineArn=SM)
    sleeps = []
    t = {"0_100": monitor.Tracked("0_100", "pidA")}
    monitor.poll_once(sf.client, SM, t, START, sleep=sleeps.append)
    assert t["0_100"].status == "SUCCEEDED" and sleeps == [2, 4]


def test_persistent_error_never_marks_failed(stubbed):
    sf = stubbed("stepfunctions")
    for _ in range(monitor.MAX_RETRIES + 1):
        sf.err("list_executions", "ThrottlingException", stateMachineArn=SM)
    t = {"0_100": monitor.Tracked("0_100", "pidA", status="RUNNING", execution_arn="e")}
    monitor.poll_once(sf.client, SM, t, START, sleep=lambda s: None)
    assert t["0_100"].status == "unknown_poll_error"


def test_terminal_claims_not_overwritten_by_poll_error(stubbed):
    sf = stubbed("stepfunctions")
    sf.err("list_executions", "InternalServerError", stateMachineArn=SM)
    t = {"0_100": monitor.Tracked("0_100", "pidA", status="SUCCEEDED", execution_arn="e")}
    monitor.poll_once(sf.client, SM, t, START, sleep=lambda s: None)
    assert t["0_100"].status == "SUCCEEDED"


def test_all_terminal():
    t = tracked()
    assert not monitor.all_terminal(t)
    for x in t.values():
        x.status = "TIMED_OUT"
    assert monitor.all_terminal(t)
    t["0_100"].status = "unknown_poll_error"
    assert not monitor.all_terminal(t)


def write_run(tmp_path, *, opened=True, env="test", claims=None):
    run = tmp_path / "runs" / "skill-1"
    run.mkdir(parents=True)
    claims = claims if claims is not None else [
        {"folder": "0_100", "pid": "pidA", "status": "launched"},
        {"folder": "1_101", "pid": "pidB", "status": "launched"},
        {"folder": "2_102", "pid": None, "status": "post_failed"}]
    plan = {"env": env, "account_id": "276553701208" if env == "test" else "072055531089",
            "profile": "ADR-TEST-MEDICALAUDIT" if env == "test" else "ADR-DEV-MEDICALAUDIT",
            "run_id": "skill-1", "live": {"state_machine_arn": SM, "workarea_bucket": "bucket",
                                          "base_prefix": "audit-processes"}}
    (run / "plan.json").write_text(json.dumps(plan))
    (run / "launch_report.json").write_text(json.dumps({
        "started_at": START.isoformat(), "claims": claims, "opened_dispatch": opened}))
    (run / "process_index.csv").write_text(
        "radicado,pid,descargado,s3uri\n0_100,pidA,false,s3://bucket/audit-processes/pidA/\n"
        "1_101,pidB,false,s3://bucket/audit-processes/pidB/\n")
    return run


def test_load_run_tracks_only_launched(tmp_path):
    run = write_run(tmp_path)
    ctx = monitor.load_run(run)
    assert list(ctx.tracked) == ["0_100", "1_101"] and ctx.opened_dispatch is True
    assert ctx.started_at == START and ctx.state_machine_arn == SM


def test_write_status(tmp_path):
    run = write_run(tmp_path)
    ctx = monitor.load_run(run)
    ctx.tracked["0_100"].status = "SUCCEEDED"
    monitor.write_status(run, ctx, datetime(2026, 11, 9, 13, tzinfo=timezone.utc))
    st = json.loads((run / "status.json").read_text())
    assert st["claims"][0] == {"folder": "0_100", "pid": "pidA", "status": "SUCCEEDED", "execution_arn": None}
    assert st["all_terminal"] is False


def test_download_claim_and_index(stubbed, tmp_path):
    run = write_run(tmp_path)
    ctx = monitor.load_run(run)
    s3 = stubbed("s3")
    prefix = "audit-processes/pidA/staging/engine/"
    s3.ok("list_objects_v2", {"Contents": [{"Key": prefix + "result.json", "Size": 2},
                                           {"Key": prefix + "sub/x.json", "Size": 2},
                                           {"Key": prefix, "Size": 0}]}, Bucket="bucket", Prefix=prefix)
    s3.ok("get_object", {"Body": stream(b"{}")}, Bucket="bucket", Key=prefix + "result.json")
    s3.ok("get_object", {"Body": stream(b"{}")}, Bucket="bucket", Key=prefix + "sub/x.json")
    n = monitor.download_claim(s3.client, ctx, ctx.tracked["0_100"], run)
    assert n == 2 and (run / "0_100" / "result.json").read_text() == "{}"
    assert (run / "0_100" / "sub" / "x.json").exists()
    assert "0_100,pidA,true" in (run / "process_index.csv").read_text()


def test_download_rejects_path_traversal(stubbed, tmp_path):
    run = write_run(tmp_path)
    ctx = monitor.load_run(run)
    s3 = stubbed("s3")
    prefix = "audit-processes/pidA/staging/engine/"
    s3.ok("list_objects_v2", {"Contents": [{"Key": prefix + "../../evil", "Size": 1}]},
          Bucket="bucket", Prefix=prefix)
    with pytest.raises(monitor.MonitorError, match="fuera"):
        monitor.download_claim(s3.client, ctx, ctx.tracked["0_100"], run)


# ---- cerrar dispatch ---------------------------------------------------------------
def live(enabled):
    d = Deployed("app", "env", "prof", 9, 1, {"values": {"dispatch": {"enabled": enabled}}})
    return LivePaths("audit-processes", "raw/", "s/", "c/", "raw/", {}, "q", [], 100, d)


def expect_close(ac, version=21, deployment=22):
    d = Deployed("app", "env", "prof", 9, 1, {"values": {"dispatch": {"enabled": True}}})
    ac.ok("list_deployment_strategies", {"Items": [
        {"Id": "strat", "Name": "adr-appconfig-seed-nobake", "DeploymentDurationInMinutes": 0,
         "FinalBakeTimeInMinutes": 0}]})
    ac.ok("create_hosted_configuration_version", {"VersionNumber": version, "ContentType": "application/json"},
          ApplicationId="app", ConfigurationProfileId="prof", Content=dispatch.build_content(d, False),
          ContentType="application/json")
    ac.ok("start_deployment", {"DeploymentNumber": deployment}, ApplicationId="app", EnvironmentId="env",
          DeploymentStrategyId="strat", ConfigurationProfileId="prof", ConfigurationVersion=str(version),
          Description=dispatch.CLOSE_MARKER)
    ac.ok("get_deployment", {"State": "COMPLETE"}, ApplicationId="app", EnvironmentId="env",
          DeploymentNumber=deployment)


def sts_ok(stubbed, account="276553701208"):
    sts = stubbed("sts")
    sts.ok("get_caller_identity", {"Account": account, "Arn": "arn:aws:iam::123456789012:user/x", "UserId": "u"})
    return sts


@pytest.mark.parametrize("mode,opened,env,expected", [
    ("auto", True, "test", True), ("auto", False, "test", False), ("auto", True, "dev", False),
    ("yes", False, "test", True), ("yes", True, "dev", True), ("no", True, "test", False)])
def test_should_close(mode, opened, env, expected):
    assert monitor.should_close(mode, opened, env) is expected


def test_close_dispatch_writes_marker(stubbed, tmp_path):
    ac, sts = stubbed("appconfig"), sts_ok(stubbed)
    expect_close(ac)
    clients = runner.Clients(appconfig=ac.client, sts=sts.client)
    monitor.close_dispatch("test", clients, lambda: live(True), execute=True, sleep=lambda s: None)


def test_close_dispatch_noop_when_already_closed(stubbed):
    ac, sts = stubbed("appconfig"), sts_ok(stubbed)
    clients = runner.Clients(appconfig=ac.client, sts=sts.client)
    assert monitor.close_dispatch("test", clients, lambda: live(False), execute=True,
                                  sleep=lambda s: None) == "ya estaba cerrado"


def test_close_dispatch_requires_execute(stubbed):
    clients = runner.Clients()
    assert "--execute" in monitor.close_dispatch("test", clients, lambda: live(True), execute=False,
                                                 sleep=lambda s: None)


def test_close_dispatch_wrong_account(stubbed):
    sts = sts_ok(stubbed, "999999999999")
    with pytest.raises(monitor.MonitorError, match="cuenta"):
        monitor.close_dispatch("test", runner.Clients(sts=sts.client), lambda: live(True), execute=True,
                               sleep=lambda s: None)


# ---- bucle -------------------------------------------------------------------------
def test_run_monitor_once_writes_status(stubbed, tmp_path):
    run = write_run(tmp_path, claims=[{"folder": "0_100", "pid": "pidA", "status": "launched"}])
    sf = stubbed("stepfunctions")
    sf.ok("list_executions", {"executions": [ex("pidA-1", "SUCCEEDED", START + timedelta(minutes=1))]},
          stateMachineArn=SM)
    out = monitor.run_monitor(run, runner.Clients(stepfunctions=sf.client), once=True, poll=30,
                              download=False, close_mode="no", execute=False, gather=None,
                              sleep=lambda s: None, now=lambda: datetime(2026, 11, 9, 13, tzinfo=timezone.utc))
    assert out["all_terminal"] is True
    assert json.loads((run / "status.json").read_text())["claims"][0]["status"] == "SUCCEEDED"


def test_run_monitor_polls_until_terminal(stubbed, tmp_path):
    run = write_run(tmp_path, claims=[{"folder": "0_100", "pid": "pidA", "status": "launched"}])
    sf = stubbed("stepfunctions")
    a = ex("pidA-1", "RUNNING", START + timedelta(minutes=1))
    sf.ok("list_executions", {"executions": [a]}, stateMachineArn=SM)
    sf.ok("describe_execution", {"executionArn": a["executionArn"], "stateMachineArn": SM, "name": "pidA-1",
                                 "status": "RUNNING", "startDate": a["startDate"], "input": "{}"},
          executionArn=a["executionArn"])
    sf.ok("list_executions", {"executions": [ex("pidA-1", "SUCCEEDED", START + timedelta(minutes=1))]},
          stateMachineArn=SM)
    sleeps = []
    out = monitor.run_monitor(run, runner.Clients(stepfunctions=sf.client), once=False, poll=30,
                              download=False, close_mode="no", execute=False, gather=None,
                              sleep=sleeps.append, now=lambda: START)
    assert out["all_terminal"] and sleeps == [30]


def test_run_monitor_downloads_and_closes_dispatch(stubbed, tmp_path):
    run = write_run(tmp_path, claims=[{"folder": "0_100", "pid": "pidA", "status": "launched"}])
    sf, s3, ac, sts = stubbed("stepfunctions"), stubbed("s3"), stubbed("appconfig"), sts_ok(stubbed)
    sf.ok("list_executions", {"executions": [ex("pidA-1", "SUCCEEDED", START + timedelta(minutes=1))]},
          stateMachineArn=SM)
    prefix = "audit-processes/pidA/staging/engine/"
    s3.ok("list_objects_v2", {"Contents": [{"Key": prefix + "r.json", "Size": 2}]}, Bucket="bucket", Prefix=prefix)
    s3.ok("get_object", {"Body": stream(b"{}")}, Bucket="bucket", Key=prefix + "r.json")
    expect_close(ac)
    clients = runner.Clients(stepfunctions=sf.client, s3=s3.client, appconfig=ac.client, sts=sts.client)
    out = monitor.run_monitor(run, clients, once=True, poll=30, download=True, close_mode="auto", execute=True,
                              gather=lambda: live(True), sleep=lambda s: None, now=lambda: START)
    assert out["downloaded"] == ["0_100"] and out["dispatch"] == "dispatch cerrado"
    assert (run / "0_100" / "r.json").exists()


def test_run_monitor_does_not_download_or_close_while_running(stubbed, tmp_path):
    run = write_run(tmp_path, claims=[{"folder": "0_100", "pid": "pidA", "status": "launched"}])
    sf = stubbed("stepfunctions")
    sf.ok("list_executions", {"executions": []}, stateMachineArn=SM)
    out = monitor.run_monitor(run, runner.Clients(stepfunctions=sf.client), once=True, poll=30, download=True,
                              close_mode="yes", execute=True, gather=None, sleep=lambda s: None, now=lambda: START)
    assert out["all_terminal"] is False and out["downloaded"] == [] and out["dispatch"] is None


def test_run_monitor_reports_status_even_if_closing_dispatch_fails(stubbed, tmp_path):
    run = write_run(tmp_path, claims=[{"folder": "0_100", "pid": "pidA", "status": "launched"}])
    sf, sts = stubbed("stepfunctions"), sts_ok(stubbed, "999999999999")
    sf.ok("list_executions", {"executions": [ex("pidA-1", "SUCCEEDED", START + timedelta(minutes=1))]},
          stateMachineArn=SM)
    out = monitor.run_monitor(run, runner.Clients(stepfunctions=sf.client, sts=sts.client), once=True, poll=30,
                              download=False, close_mode="yes", execute=True, gather=lambda: live(True),
                              sleep=lambda s: None, now=lambda: START)
    assert out["all_terminal"] and out["dispatch_error"] and "cuenta" in out["dispatch"]
    assert (run / "status.json").exists()


def test_run_monitor_gives_up_after_many_poll_error_cycles(stubbed, tmp_path):
    run = write_run(tmp_path, claims=[{"folder": "0_100", "pid": "pidA", "status": "launched"}])
    sf = stubbed("stepfunctions")
    for _ in range(monitor.MAX_UNKNOWN_CYCLES):
        sf.err("list_executions", "InternalServerError", stateMachineArn=SM)
    out = monitor.run_monitor(run, runner.Clients(stepfunctions=sf.client), once=False, poll=30, download=False,
                              close_mode="no", execute=False, gather=None, sleep=lambda s: None, now=lambda: START)
    assert "gave_up" in out and out["claims"][0]["status"] == "unknown_poll_error"
