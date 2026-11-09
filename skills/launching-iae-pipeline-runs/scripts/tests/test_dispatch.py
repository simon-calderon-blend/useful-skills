import json

import pytest

from iae_launch import dispatch
from iae_launch.live import Deployed

DOC = {"version": "1", "_createdAt": "x",
       "flags": {"dispatch": {"name": "dispatch", "_updatedAt": "y"}},
       "values": {"dispatch": {"enabled": True, "maxMessagesPerCycle": 10, "_createdAt": "z"}}}


def deployed(content=DOC):
    return Deployed("app", "env", "prof", 5, 9, content)


def expected_content(enabled):
    doc = json.loads(json.dumps(DOC))
    doc.pop("_createdAt")
    doc["flags"]["dispatch"].pop("_updatedAt")
    doc["values"]["dispatch"].pop("_createdAt")
    doc["values"]["dispatch"]["enabled"] = enabled
    return json.dumps(doc).encode()


class Clock:
    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def queue_set(sc, enabled, states, desc=None, new_version=11):
    sc.ok("create_hosted_configuration_version",
          {"VersionNumber": new_version, "ContentType": "application/json"},
          ApplicationId="app", ConfigurationProfileId="prof", Content=expected_content(enabled),
          ContentType="application/json")
    params = dict(ApplicationId="app", EnvironmentId="env", DeploymentStrategyId="strat",
                  ConfigurationProfileId="prof", ConfigurationVersion=str(new_version))
    if desc:
        params["Description"] = desc
    sc.ok("start_deployment", {"DeploymentNumber": 12}, **params)
    for s in states:
        sc.ok("get_deployment", {"State": s}, ApplicationId="app", EnvironmentId="env",
              DeploymentNumber=12)


def test_set_enabled_uses_deployed_content_strips_underscore_keys(stubbed):
    sc = stubbed("appconfig")
    queue_set(sc, False, ["DEPLOYING", "COMPLETE"])
    clk = Clock()
    n = dispatch.set_enabled(sc.client, deployed(), "strat", False, sleep=clk.sleep, clock=clk.now)
    assert n.number == 12 and clk.t == 2.0


def test_description_only_when_given(stubbed):
    sc = stubbed("appconfig")
    queue_set(sc, False, ["COMPLETE"], desc=dispatch.CLOSE_MARKER)
    dispatch.set_enabled(sc.client, deployed(), "strat", False, description=dispatch.CLOSE_MARKER,
                         sleep=lambda s: None)


@pytest.mark.parametrize("state", ["ROLLED_BACK", "REVERTED"])
def test_rollback_raises(stubbed, state):
    sc = stubbed("appconfig")
    queue_set(sc, True, [state])
    with pytest.raises(dispatch.DispatchError, match=state):
        dispatch.set_enabled(sc.client, deployed(), "strat", True, sleep=lambda s: None)


def test_timeout(stubbed):
    sc = stubbed("appconfig")
    queue_set(sc, True, ["DEPLOYING"] * 80)
    clk = Clock()
    with pytest.raises(dispatch.DispatchError, match="120"):
        dispatch.set_enabled(sc.client, deployed(), "strat", True, sleep=clk.sleep, clock=clk.now)
    sc.stub._queue.clear()  # los get_deployment sobrantes no importan


def test_read_enabled():
    assert dispatch.read_enabled(deployed()) is True
    assert dispatch.read_enabled(deployed({"values": {}})) is False


def strategy(name, dur, bake, sid="s"):
    return {"Id": sid, "Name": name, "DeploymentDurationInMinutes": dur, "FinalBakeTimeInMinutes": bake}


def test_strategy_prefers_named_and_validates_behaviour(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_deployment_strategies", {"Items": [
        strategy("instant-0bake", 0, 0, "b"), strategy("adr-appconfig-seed-nobake", 0, 5, "bad"),
        strategy("adr-appconfig-seed-nobake", 0, 0, "good")]})
    # el primero con nombre preferido y 0/0 manda; el de bake 5 no vale
    assert dispatch.resolve_strategy_id(sc.client) == "good"


def test_strategy_fallback_skips_managed(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_deployment_strategies", {"Items": [
        strategy("AppConfig.AllAtOnce", 0, 0, "AppConfig.AllAtOnce"), strategy("anomaly-x", 0, 0, "zz")]})
    assert dispatch.resolve_strategy_id(sc.client) == "zz"


def test_strategy_none(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_deployment_strategies", {"Items": [strategy("slow", 10, 10, "q")]})
    assert dispatch.resolve_strategy_id(sc.client) is None


def _list_then_get(sc, newest_desc):
    # list_deployments NO devuelve Description (resumen): hay que get_deployment del último.
    sc.ok("list_deployments", {"Items": [
        {"DeploymentNumber": 3, "ConfigurationName": "dispatch", "State": "COMPLETE"},
        {"DeploymentNumber": 7, "ConfigurationName": "dispatch", "State": "COMPLETE"},
        {"DeploymentNumber": 8, "ConfigurationName": "dispatch", "State": "ROLLED_BACK"},
        {"DeploymentNumber": 9, "ConfigurationName": "other", "State": "COMPLETE"}]},
        ApplicationId="app", EnvironmentId="env")
    sc.ok("get_deployment", {"Description": newest_desc, "DeploymentNumber": 7},
          ApplicationId="app", EnvironmentId="env", DeploymentNumber=7)


def test_closed_by_marker(stubbed):
    sc = stubbed("appconfig")
    _list_then_get(sc, dispatch.CLOSE_MARKER)
    assert dispatch.closed_by_marker(sc.client, deployed()) is True


def test_not_closed_by_marker(stubbed):
    sc = stubbed("appconfig")
    _list_then_get(sc, "operador")
    assert dispatch.closed_by_marker(sc.client, deployed()) is False


def test_closed_by_marker_no_deployments(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_deployments", {"Items": []}, ApplicationId="app", EnvironmentId="env")
    assert dispatch.closed_by_marker(sc.client, deployed()) is False


def test_breadcrumb_roundtrip(tmp_path):
    p = dispatch.write_breadcrumb("test", tmp_path, app="a", was_enabled=False, restore_to=True,
                                  run_id="r1", pid=42)
    assert p == tmp_path / "launching-iae-pipeline-runs" / "paused-test.json"
    data = dispatch.read_breadcrumb("test", tmp_path)
    assert data["restore_to"] is True and data["run_id"] == "r1" and data["pid"] == 42
    assert "started_at" in data
    dispatch.delete_breadcrumb("test", tmp_path)
    assert dispatch.read_breadcrumb("test", tmp_path) is None
    dispatch.delete_breadcrumb("test", tmp_path)  # idempotente


def test_foreign_breadcrumbs_lists_both_tools(tmp_path):
    (tmp_path / "pipeline-runner").mkdir()
    (tmp_path / "pipeline-runner" / "paused-dev.json").write_text("{}")
    dispatch.write_breadcrumb("dev", tmp_path, app="a", was_enabled=True, restore_to=True,
                              run_id="r", pid=1)
    found = dispatch.existing_breadcrumbs("dev", tmp_path)
    assert {p.parent.name for p in found} == {"pipeline-runner", "launching-iae-pipeline-runs"}
    assert dispatch.existing_breadcrumbs("test", tmp_path) == []


def test_state_home_env(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    assert dispatch.state_home() == tmp_path
    monkeypatch.delenv("XDG_STATE_HOME")
    assert str(dispatch.state_home()).endswith(".local/state")


def test_compute_restore_to():
    assert dispatch.compute_restore_to(was_enabled=True, closed_by_marker=False, allow_open=False) is True
    assert dispatch.compute_restore_to(False, True, False) is True
    assert dispatch.compute_restore_to(False, False, True) is True
    assert dispatch.compute_restore_to(False, False, False) is False


def test_strip_only_appconfig_metadata_keys():
    d = Deployed("app", "env", "prof", 5, 9, {"values": {"dispatch": {"enabled": True, "_custom": 1,
                                                                        "_createdAt": "x"}}})
    doc = json.loads(dispatch.build_content(d, False))
    assert doc["values"]["dispatch"] == {"enabled": False, "_custom": 1}


def test_set_enabled_returns_completion_time(stubbed):
    from datetime import datetime, timezone
    sc = stubbed("appconfig")
    queue_set(sc, False, [])
    done = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
    sc.ok("get_deployment", {"State": "COMPLETE", "CompletedAt": done}, ApplicationId="app",
          EnvironmentId="env", DeploymentNumber=12)
    assert dispatch.set_enabled(sc.client, deployed(), "strat", False, sleep=lambda s: None).completed_at == done


def conflict(sc):
    sc.err("create_hosted_configuration_version", "ConflictException", ApplicationId="app",
           ConfigurationProfileId="prof", Content=expected_content(True), ContentType="application/json")


def test_set_enabled_fresh_uses_fresh_document_and_waits_for_idle(stubbed):
    sc = stubbed("appconfig")
    queue_set(sc, True, ["COMPLETE"])
    reads = [Deployed("app", "env", "prof", 5, 9, DOC, (4,)), Deployed("app", "env", "prof", 5, 9, DOC)]
    sleeps = []
    out = dispatch.set_enabled_fresh(sc.client, lambda: reads.pop(0), "strat", True, sleep=sleeps.append)
    assert out.number == 12 and sleeps == [dispatch.POLL_INTERVAL] and reads == []


def test_set_enabled_fresh_waits_idle_timeout():
    clk = Clock()
    busy = Deployed("app", "env", "prof", 5, 9, DOC, (4,))
    with pytest.raises(dispatch.DispatchError, match="en curso"):
        dispatch.set_enabled_fresh(None, lambda: busy, "strat", True, sleep=clk.sleep, clock=clk.now)


def test_set_enabled_fresh_retries_conflict_with_backoff(stubbed):
    sc = stubbed("appconfig")
    conflict(sc)
    conflict(sc)
    queue_set(sc, True, ["COMPLETE"])
    sleeps = []
    out = dispatch.set_enabled_fresh(sc.client, deployed, "strat", True, sleep=sleeps.append)
    assert out.number == 12 and sleeps == [5.0, 10.0]


def test_set_enabled_fresh_gives_up_after_attempts(stubbed):
    sc = stubbed("appconfig")
    for _ in range(dispatch.RETRY_ATTEMPTS):
        conflict(sc)
    from botocore.exceptions import ClientError
    with pytest.raises(ClientError):
        dispatch.set_enabled_fresh(sc.client, deployed, "strat", True, sleep=lambda s: None)


def test_set_enabled_fresh_does_not_retry_other_errors(stubbed):
    sc = stubbed("appconfig")
    sc.err("create_hosted_configuration_version", "BadRequestException", ApplicationId="app",
           ConfigurationProfileId="prof", Content=expected_content(True), ContentType="application/json")
    from botocore.exceptions import ClientError
    with pytest.raises(ClientError):
        dispatch.set_enabled_fresh(sc.client, deployed, "strat", True, sleep=lambda s: None)


def test_latest_time_ignores_non_complete(stubbed):
    from datetime import datetime, timezone
    sc = stubbed("appconfig")
    sc.ok("list_deployments", {"Items": [
        {"DeploymentNumber": 3, "ConfigurationName": "dispatch", "State": "COMPLETE"},
        {"DeploymentNumber": 4, "ConfigurationName": "dispatch", "State": "DEPLOYING"}]},
        ApplicationId="app", EnvironmentId="env")
    done = datetime(2026, 1, 1, tzinfo=timezone.utc)
    sc.ok("get_deployment", {"DeploymentNumber": 3, "CompletedAt": done}, ApplicationId="app",
          EnvironmentId="env", DeploymentNumber=3)
    assert dispatch.latest_dispatch_time(sc.client, deployed()) == done


def test_breadcrumb_is_exclusive(tmp_path):
    dispatch.write_breadcrumb("dev", tmp_path, app="a", was_enabled=True, restore_to=True, run_id="r", pid=1)
    with pytest.raises(dispatch.BreadcrumbExists):
        dispatch.write_breadcrumb("dev", tmp_path, app="a", was_enabled=True, restore_to=True, run_id="r2", pid=2)
    assert dispatch.read_breadcrumb("dev", tmp_path)["run_id"] == "r"
    assert [p.name for p in (tmp_path / "launching-iae-pipeline-runs").iterdir()] == ["paused-dev.json"]


def test_pid_alive():
    import os
    assert dispatch.pid_alive(os.getpid()) is True
    assert dispatch.pid_alive(2 ** 22 + 12345) is False
