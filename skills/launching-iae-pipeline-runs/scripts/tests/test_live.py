import pytest

from iae_launch import live
from tests.conftest import stream

APP = {"Name": "adr-dev-medicalaudit-api-appconfig", "Id": "app1"}
DECOY = {"Name": "e1-adr-dev-medicalaudit-api-appconfig", "Id": "decoy"}


def queue_lookup(sc, deployments, *, apps=None, envs=None, profiles=None, content=None, version=7):
    sc.ok("list_applications", {"Items": apps or [DECOY, APP]})
    sc.ok("list_environments", {"Items": envs or [{"Name": "dev", "Id": "env1"}]},
          ApplicationId="app1")
    sc.ok("list_configuration_profiles",
          {"Items": profiles or [{"Name": "storage", "Id": "prof1"}]}, ApplicationId="app1")
    sc.ok("list_deployments", {"Items": deployments}, ApplicationId="app1", EnvironmentId="env1")
    if content is not None:
        sc.ok("get_hosted_configuration_version",
              {"Content": stream(content), "ContentType": "application/json"},
              ApplicationId="app1", ConfigurationProfileId="prof1", VersionNumber=version)


def dep(n, state, version, name="storage"):
    return {"DeploymentNumber": n, "State": state, "ConfigurationName": name,
            "ConfigurationVersion": str(version)}


def test_deployed_config_uses_latest_complete_not_latest_hosted(stubbed):
    sc = stubbed("appconfig")
    queue_lookup(sc, [dep(3, "COMPLETE", 4), dep(5, "COMPLETE", 7), dep(6, "DEPLOYING", 8),
                      dep(9, "COMPLETE", 99, name="other")],
                 content={"output": {"intake": "raw/"}}, version=7)
    d = live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev", "storage")
    assert (d.app_id, d.env_id, d.profile_id) == ("app1", "env1", "prof1")
    assert (d.version, d.deployment_number) == (7, 5)
    assert d.content == {"output": {"intake": "raw/"}}
    assert d.in_progress == (6,)


@pytest.mark.parametrize("state", ["DEPLOYING", "BAKING", "VALIDATING", "ROLLING_BACK"])
def test_in_progress_states(stubbed, state):
    sc = stubbed("appconfig")
    queue_lookup(sc, [dep(1, "COMPLETE", 1), dep(2, state, 2)], content={}, version=1)
    assert live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev",
                                "storage").in_progress == (2,)


def test_missing_app_is_exact_match(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_applications", {"Items": [DECOY]})
    with pytest.raises(live.LiveConfigError, match="aplicación"):
        live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev", "storage")


def test_missing_environment(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_applications", {"Items": [APP]})
    sc.ok("list_environments", {"Items": [{"Name": "other", "Id": "e"}]}, ApplicationId="app1")
    with pytest.raises(live.LiveConfigError, match="ambiente"):
        live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev", "storage")


def test_missing_profile(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_applications", {"Items": [APP]})
    sc.ok("list_environments", {"Items": [{"Name": "dev", "Id": "env1"}]}, ApplicationId="app1")
    sc.ok("list_configuration_profiles", {"Items": []}, ApplicationId="app1")
    with pytest.raises(live.LiveConfigError, match="perfil"):
        live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev", "storage")


def test_no_complete_deployment(stubbed):
    sc = stubbed("appconfig")
    queue_lookup(sc, [dep(1, "ROLLED_BACK", 1)])
    with pytest.raises(live.LiveConfigError, match="COMPLETE"):
        live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev", "storage")


def test_deployments_paginated(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_applications", {"Items": [APP]})
    sc.ok("list_environments", {"Items": [{"Name": "dev", "Id": "env1"}]}, ApplicationId="app1")
    sc.ok("list_configuration_profiles", {"Items": [{"Name": "storage", "Id": "prof1"}]},
          ApplicationId="app1")
    sc.ok("list_deployments", {"Items": [dep(1, "COMPLETE", 1)], "NextToken": "t"},
          ApplicationId="app1", EnvironmentId="env1")
    sc.ok("list_deployments", {"Items": [dep(2, "COMPLETE", 2)]},
          ApplicationId="app1", EnvironmentId="env1", NextToken="t")
    sc.ok("get_hosted_configuration_version", {"Content": stream({"a": 1})},
          ApplicationId="app1", ConfigurationProfileId="prof1", VersionNumber=2)
    assert live.deployed_config(sc.client, "adr-dev-medicalaudit-api-appconfig", "dev",
                                "storage").deployment_number == 2


# ---- gather_live_paths (loader inyectado) -----------------------------------
def D(content, version=1, in_progress=()):
    return live.Deployed("a", "e", "p", version, 1, content, tuple(in_progress))


def fake_loader(overrides=None):
    docs = {
        ("api", "storage"): D({"output": {"intake": "raw/"}}, 6),
        ("doc-extraction", "storage"): D({"output": {"structured": "staging/document-extraction/artifacts/"},
                                          "work": {"consolidated": "staging/document-extraction/consolidated/"}}, 5),
        ("doc-extraction", "batch"): D({"min_records_per_job": 100}, 3),
        ("fetch-claim-invoice-details", "storage"): D({"output": "raw/"}, 2),
        ("intelligent-audit-engine", "engine_ingest_mappings"): D({"mappings": {"raw/": {}, "staging/document-extraction/artifacts/": {}}}, 6),
        ("intelligent-audit-engine", "runtime"): D({"qualifier": "v4_16_0"}, 18),
        ("prerequisite-engine", "minimum-requirements"): D({"rules": [{"id": "r"}]}, 1),
        ("throttle-controller", "dispatch"): D({"values": {"dispatch": {"enabled": True}}}, 9),
    }
    docs.update(overrides or {})

    def load(app, profile):
        return docs[(app, profile)]
    return load


def test_gather_live_paths():
    lp = live.gather_live_paths(fake_loader())
    assert lp.intake == "raw/"
    assert lp.structured == "staging/document-extraction/artifacts/"
    assert lp.consolidated == "staging/document-extraction/consolidated/"
    assert lp.invoice_output == "raw/"
    assert lp.qualifier == "v4_16_0"
    assert lp.rules == [{"id": "r"}]
    assert lp.min_records_per_job == 100
    assert lp.base_prefix == "audit-processes"
    assert lp.versions["api/storage"] == 6
    assert lp.versions["throttle-controller/dispatch"] == 9


def test_min_records_default_when_key_absent():
    lp = live.gather_live_paths(fake_loader({("doc-extraction", "batch"): D({})}))
    assert lp.min_records_per_job == 100


def test_gather_fails_when_key_missing():
    with pytest.raises(live.LiveConfigError, match="output.intake"):
        live.gather_live_paths(fake_loader({("api", "storage"): D({"output": {}})}))


def test_ingest_mismatches_empty_when_consistent():
    assert live.ingest_mismatches(live.gather_live_paths(fake_loader())) == []


def test_ingest_mismatches_reports_missing_prefix():
    lp = live.gather_live_paths(fake_loader({
        ("intelligent-audit-engine", "engine_ingest_mappings"): D({"mappings": {"raw/": {}}})}))
    assert live.ingest_mismatches(lp) == ["staging/document-extraction/artifacts/"]


def test_in_progress_listed():
    lp = live.gather_live_paths(fake_loader({("api", "storage"): D({"output": {"intake": "raw/"}}, 6, [4])}))
    assert lp.in_progress == {"api/storage": (4,)}


def test_versions_snapshot_drift():
    a = live.gather_live_paths(fake_loader())
    b = live.gather_live_paths(fake_loader({("api", "storage"): D({"output": {"intake": "raw/"}}, 7)}))
    assert live.version_drift(a.versions, b.versions) == {"api/storage": (6, 7)}
    assert live.version_drift(a.versions, a.versions) == {}


# ---- API gateway / SFN / bucket / queue -------------------------------------
def test_api_base_url(stubbed):
    ag = stubbed("apigateway")
    ag.ok("get_rest_apis", {"items": [{"id": "zzz", "name": "adr-dev-medicalaudit-api-gateway-copy"},
                                      {"id": "abc123", "name": "adr-dev-medicalaudit-api-gateway"}]})
    ag.ok("get_stages", {"item": [{"stageName": "v1"}]}, restApiId="abc123")
    assert live.api_base_url(ag.client, "dev") == "https://abc123.execute-api.us-east-1.amazonaws.com/v1"


def test_api_missing_stage(stubbed):
    ag = stubbed("apigateway")
    ag.ok("get_rest_apis", {"items": [{"id": "abc123", "name": "adr-dev-medicalaudit-api-gateway"}]})
    ag.ok("get_stages", {"item": [{"stageName": "v2"}]}, restApiId="abc123")
    with pytest.raises(live.LiveConfigError, match="v1"):
        live.api_base_url(ag.client, "dev")


def test_api_missing(stubbed):
    ag = stubbed("apigateway")
    ag.ok("get_rest_apis", {"items": []})
    with pytest.raises(live.LiveConfigError):
        live.api_base_url(ag.client, "dev")


def test_state_machine_arn(stubbed):
    sf = stubbed("stepfunctions")
    arn = "arn:aws:states:us-east-1:1:stateMachine:adr-dev-medicalaudit-pipeline"
    sf.ok("list_state_machines", {"stateMachines": [
        {"name": "adr-dev-medicalaudit-pipeline-x", "stateMachineArn": "arn:x", "type": "STANDARD",
         "creationDate": 0},
        {"name": "adr-dev-medicalaudit-pipeline", "stateMachineArn": arn, "type": "STANDARD",
         "creationDate": 0}]})
    assert live.state_machine_arn(sf.client, "dev") == arn


def test_state_machine_missing(stubbed):
    sf = stubbed("stepfunctions")
    sf.ok("list_state_machines", {"stateMachines": []})
    with pytest.raises(live.LiveConfigError):
        live.state_machine_arn(sf.client, "dev")


def test_workarea_bucket(stubbed):
    s3 = stubbed("s3")
    s3.ok("head_bucket", {}, Bucket="adr-dev-medicalaudit-workarea")
    assert live.workarea_bucket(s3.client, "dev") == "adr-dev-medicalaudit-workarea"


def test_conveyor_queue_url(stubbed):
    sqs = stubbed("sqs")
    sqs.ok("get_queue_url", {"QueueUrl": "https://q"},
           QueueName="adr-dev-medicalaudit-doc-extraction-chunks-conveyor")
    assert live.conveyor_queue_url(sqs.client, "dev") == "https://q"


@pytest.mark.parametrize("bad", ["raw", "/raw/", "a/../b/", 5])
def test_prefix_validation(bad):
    with pytest.raises(live.LiveConfigError, match="prefijo intake"):
        live.gather_live_paths(fake_loader({("api", "storage"): D({"output": {"intake": bad}})}))
