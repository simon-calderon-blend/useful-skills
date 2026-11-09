"""Addendum v2: espera de la línea OFF del throttle controller, leave-closed, open-dispatch, stop-run."""
import json
from datetime import datetime, timedelta, timezone

import pytest
from botocore.stub import ANY

from iae_launch import dispatch, launcher
from tests.test_launcher import Harness, breadcrumb, drain, make_plan

GROUP = "/aws/lambda/adr-dev-medicalaudit-api-throttle-controller"
PATTERN = '"Dispatch feature flag is OFF"'
SINCE = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
SINCE_MS = int(SINCE.timestamp() * 1000)


class Clock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s


def log_ok(logs, messages, token=None):
    resp = {"events": [{"message": m, "timestamp": 1} for m in messages]}
    if token:
        resp["nextToken"] = token
    logs.ok("filter_log_events", resp, logGroupName=GROUP, startTime=SINCE_MS, filterPattern=PATTERN)


def test_off_found_immediately(stubbed):
    logs = stubbed("logs")
    log_ok(logs, ["START", "Dispatch feature flag is OFF, skipping"])
    clk = Clock()
    launcher.wait_for_off(logs.client, "dev", SINCE, sleep=clk.sleep, clock=clk.now)
    assert clk.sleeps == []


def test_only_enabled_lines_keep_waiting_then_off(stubbed):
    logs = stubbed("logs")
    log_ok(logs, ["Dispatch enabled, draining"])
    log_ok(logs, ["Dispatch feature flag is OFF"])
    clk = Clock()
    launcher.wait_for_off(logs.client, "dev", SINCE, sleep=clk.sleep, clock=clk.now)
    assert clk.sleeps == [launcher.OFF_POLL]


def test_off_follows_next_token(stubbed):
    logs = stubbed("logs")
    log_ok(logs, ["otra línea"], token="n1")
    logs.ok("filter_log_events", {"events": [{"message": "Dispatch feature flag is OFF", "timestamp": 2}]},
            logGroupName=GROUP, startTime=SINCE_MS, filterPattern=PATTERN, nextToken="n1")
    clk = Clock()
    launcher.wait_for_off(logs.client, "dev", SINCE, sleep=clk.sleep, clock=clk.now)
    assert clk.sleeps == []


def test_off_timeout_raises(stubbed):
    logs = stubbed("logs")
    for _ in range(40):
        log_ok(logs, ["Dispatch enabled"])
    clk = Clock()
    with pytest.raises(dispatch.DispatchError, match="OFF"):
        launcher.wait_for_off(logs.client, "dev", SINCE, sleep=clk.sleep, clock=clk.now)
    assert clk.t >= launcher.OFF_TIMEOUT
    logs.stub._queue.clear()


def test_launch_aborts_and_restores_when_off_never_appears(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    clk = Clock()
    h.deps.clock, h.deps.sleep = clk.now, clk.sleep
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    for _ in range(40):
        h.logs.ok("filter_log_events", {"events": [{"message": "Dispatch enabled", "timestamp": 1}]},
                  logGroupName=GROUP, startTime=ANY, filterPattern=PATTERN)
    h.expect_dispatch_flip(True, 13, 14)
    out = h.run(path, plan)
    assert out.exit_code == 1 and "OFF" in out.report["error"] and h.api.posted == []
    assert not breadcrumb(tmp_path).exists()
    h.logs.stub._queue.clear()


def test_latest_dispatch_deployment_time(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path)
    drain(h)
    h.expect_latest_deployment_time()
    assert dispatch.latest_dispatch_time(h.ac.client, h.live.dispatch) == datetime(2026, 11, 9, 11, 0, tzinfo=timezone.utc)
    h.ac.ok("list_deployments", {"Items": []}, ApplicationId="app", EnvironmentId="env")
    assert dispatch.latest_dispatch_time(h.ac.client, h.live.dispatch) is None


# ---- leave-closed ------------------------------------------------------------------------
def test_leave_dispatch_closed_does_not_restore(stubbed, tmp_path):
    path, plan = make_plan(tmp_path, claims_n=1)
    h = Harness(stubbed, tmp_path)
    h.expect_strategy()
    h.expect_dispatch_flip(False, 11, 12)
    h.expect_off()
    h.expect_puts(1)
    out = h.run(path, plan, leave_closed=True)
    assert out.exit_code == 0
    assert out.report["dispatch"] == {"before": True, "after": False, "restore_to": False}
    assert out.report["left_closed"] is True and out.report["opened_dispatch"] is False
    assert not breadcrumb(tmp_path).exists()


# ---- open-dispatch --------------------------------------------------------------------------
def test_open_dispatch_opens_when_closed(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path, enabled=False)
    h.expect_strategy()
    h.expect_dispatch_flip(True, 13, 14)
    out = launcher.open_dispatch("dev", h.deps, execute=True)
    assert out.exit_code == 0 and out.report["open"] == "abierto"


def test_open_dispatch_noop_if_open_and_needs_execute(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path, enabled=True)
    assert launcher.open_dispatch("dev", h.deps, execute=True).report["open"] == "ya estaba abierto"
    h2 = Harness(stubbed, tmp_path, enabled=False)
    drain(h2)
    assert "--execute" in launcher.open_dispatch("dev", h2.deps, execute=False).report["open"]


# ---- stop-run ------------------------------------------------------------------------------
SM = "arn:aws:states:us-east-1:072055531089:stateMachine:adr-dev-medicalaudit-pipeline"


def run_dir(tmp_path):
    run = tmp_path / "runs" / "skill-1"
    run.mkdir(parents=True)
    plan = {"env": "dev", "account_id": "072055531089", "profile": "ADR-DEV-MEDICALAUDIT", "run_id": "skill-1",
            "live": {"state_machine_arn": SM, "workarea_bucket": "adr-dev-medicalaudit-workarea", "base_prefix": "audit-processes"}}
    (run / "plan.json").write_text(json.dumps(plan))
    (run / "launch_report.json").write_text(json.dumps({
        "started_at": SINCE.isoformat(), "opened_dispatch": False, "claims": [
            {"folder": "0_100", "pid": "pidA", "status": "launched"},
            {"folder": "1_101", "pid": "pidB", "status": "launched"}]}))
    return run


def execution(name):
    return {"executionArn": f"arn:aws:states:us-east-1:072055531089:execution:adr:{name}",
            "stateMachineArn": SM, "name": name, "status": "RUNNING", "startDate": SINCE + timedelta(minutes=1)}


def tracker_get(ddb, pid, status):
    ddb.ok("get_item", {"Item": {"status": {"S": status}}} if status else {},
           TableName="adr-dev-medicalaudit-tracker-data", Key={"process_id": {"S": pid}},
           ProjectionExpression="#s", ExpressionAttributeNames={"#s": "status"})


def stop_harness(stubbed, tmp_path):
    h = Harness(stubbed, tmp_path)
    h.sf, h.ddb = stubbed("stepfunctions"), stubbed("dynamodb")
    h.deps.clients._cache.update(stepfunctions=h.sf.client, dynamodb=h.ddb.client)
    return h


def test_stop_run_stops_only_this_runs_pids_and_verifies_tracker(stubbed, tmp_path):
    run = run_dir(tmp_path)
    h = stop_harness(stubbed, tmp_path)
    a, other = execution("pidA-1"), execution("zzz-1")
    h.sf.ok("list_executions", {"executions": [other, a]}, stateMachineArn=SM, statusFilter="RUNNING")
    h.sf.ok("stop_execution", {"stopDate": SINCE}, executionArn=a["executionArn"], error="Relaunch",
            cause="cambio de qualifier")
    tracker_get(h.ddb, "pidA", "SF_RUNNING")
    tracker_get(h.ddb, "pidB", "SF_SUCCEEDED")
    tracker_get(h.ddb, "pidA", "SF_ABORTED")
    out = launcher.stop_run(run, h.deps, execute=True, cause="cambio de qualifier")
    assert out.exit_code == 0
    assert out.report["stopped"] == ["pidA"]
    assert out.report["tracker"] == {"pidA": "SF_ABORTED", "pidB": "SF_SUCCEEDED"}


def test_stop_run_tracker_not_terminal_exit_3(stubbed, tmp_path):
    run = run_dir(tmp_path)
    h = stop_harness(stubbed, tmp_path)
    a = execution("pidA-1")
    h.sf.ok("list_executions", {"executions": [a]}, stateMachineArn=SM, statusFilter="RUNNING")
    h.sf.ok("stop_execution", {"stopDate": SINCE}, executionArn=a["executionArn"], error="Relaunch", cause="x")
    clk = Clock()
    h.deps.clock, h.deps.sleep = clk.now, clk.sleep
    for _ in range(40):
        tracker_get(h.ddb, "pidA", "SF_RUNNING")
        tracker_get(h.ddb, "pidB", None)
    out = launcher.stop_run(run, h.deps, execute=True, cause="x")
    assert out.exit_code == 3 and out.report["tracker"]["pidA"] == "SF_RUNNING"
    h.ddb.stub._queue.clear()


def test_stop_run_without_execute_is_read_only(stubbed, tmp_path):
    run = run_dir(tmp_path)
    h = stop_harness(stubbed, tmp_path)
    drain(h)
    h.sf.ok("list_executions", {"executions": [execution("pidB-9")]}, stateMachineArn=SM, statusFilter="RUNNING")
    out = launcher.stop_run(run, h.deps, execute=False, cause="x")
    assert out.exit_code == 0 and out.report["would_stop"] == ["pidB"]


def test_stop_run_wrong_account_aborts(stubbed, tmp_path):
    run = run_dir(tmp_path)
    h = Harness(stubbed, tmp_path, account="999999999999")
    out = launcher.stop_run(run, h.deps, execute=True, cause="x")
    assert out.exit_code == 1 and "999999999999" in out.report["abort"]
