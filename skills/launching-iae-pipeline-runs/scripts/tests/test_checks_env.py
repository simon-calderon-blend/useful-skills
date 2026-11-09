import base64
import hashlib
import json
from datetime import datetime, timedelta, timezone

import pytest
from botocore.exceptions import ClientError

from iae_launch import auth, checks, dispatch, envs
from iae_launch.live import Deployed, LivePaths

DEV = envs.get_env("dev")
NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)


def lp(**kw):
    d = Deployed("a", "e", "p", 9, 1, {"values": {"dispatch": {"enabled": True}}})
    base = dict(base_prefix="audit-processes", intake="raw/", structured="staging/s/",
                consolidated="staging/c/", invoice_output="raw/",
                ingest_mappings={"raw/": {}, "staging/s/": {}}, qualifier="v4_16_0", rules=[],
                min_records_per_job=100, dispatch=d, versions={"api/storage": 1})
    base.update(kw)
    return LivePaths(**base)


# ---- Check / Report ------------------------------------------------------
def test_report_ok_and_json():
    r = checks.Report([checks.Check("a", "ok", "d", "p"), checks.Check("b", "warn", "d", "p"),
                       checks.Check("c", "skipped", "d", "p")])
    assert r.ok
    assert json.loads(r.to_json())["ok"] is True
    r2 = checks.Report([checks.Check("a", "FAILED", "d", "p")])
    assert not r2.ok and json.loads(r2.to_json())["checks"][0]["status"] == "FAILED"


def ce(code):
    return ClientError({"Error": {"Code": code, "Message": "m"}}, "Op")


def test_guarded_ok_passthrough():
    c = checks.guarded("aws_identity", lambda: ("ok", "fine"))
    assert (c.name, c.status, c.detail, c.prevents) == (
        "aws_identity", "ok", "fine", checks.PREVENTS["aws_identity"])


@pytest.mark.parametrize("exc", [ce("AccessDenied"), ce("AccessDeniedException")])
def test_guarded_access_denied_is_skipped(exc):
    def boom():
        raise exc
    c = checks.guarded("aws_identity", boom)
    assert c.status == "skipped" and "AccessDenied" in c.detail


@pytest.mark.parametrize("exc", [ce("ExpiredToken"), RuntimeError("Token has expired and refresh failed"),
                                 RuntimeError("LoginRefreshRequired"), RuntimeError("UnauthorizedSSOToken")])
def test_guarded_sso_expired(exc):
    def boom():
        raise exc
    c = checks.guarded("aws_identity", boom)
    assert c.status == "FAILED"
    assert c.detail == "Sesión SSO expirada: pide al usuario correr 'awsl' (no lo ejecutes)."


def test_guarded_other_exception_failed_with_class_and_message():
    def boom():
        raise ValueError("kaput")
    c = checks.guarded("aws_identity", boom)
    assert c.status == "FAILED" and "ValueError" in c.detail and "kaput" in c.detail


# ---- profile --------------------------------------------------------------
def test_profile_not_sensitive():
    assert checks.check_profile_not_sensitive("ADR-DEV-MEDICALAUDIT").status == "ok"
    assert checks.check_profile_not_sensitive("ADR-PROD-X").status == "FAILED"


CONFIG = """[profile ADR-DEV-MEDICALAUDIT]
sso_session = ADRES-ORGANIZATION
sso_account_id = 1

[sso-session ADRES-ORGANIZATION]
sso_start_url = https://x
"""


def test_profile_in_config(tmp_path):
    cfg = tmp_path / "config"
    cfg.write_text(CONFIG)
    assert checks.check_profile_in_config("ADR-DEV-MEDICALAUDIT", cfg).status == "ok"
    bad = checks.check_profile_in_config("ADRES-TEST-MEDICAL-AUDIT-1", cfg)
    assert bad.status == "FAILED" and "ADRES-TEST-MEDICAL-AUDIT-1" in bad.detail


def test_profile_in_config_missing_file(tmp_path):
    assert checks.check_profile_in_config("X", tmp_path / "nope").status == "FAILED"


# ---- identity ---------------------------------------------------------------
def test_identity_ok_and_wrong_account(stubbed):
    sts = stubbed("sts")
    sts.ok("get_caller_identity", {"Account": "072055531089", "Arn": "arn:aws:iam::123456789012:user/x", "UserId": "u"})
    assert checks.check_aws_identity(sts.client, DEV).status == "ok"
    sts.ok("get_caller_identity", {"Account": "999999999999", "Arn": "arn:aws:iam::123456789012:user/x", "UserId": "u"})
    c = checks.check_aws_identity(sts.client, DEV)
    assert c.status == "FAILED" and "999999999999" in c.detail


# ---- sso remaining ------------------------------------------------------------
def cache_file(cache, session, expires_at):
    name = hashlib.sha1(session.encode(), usedforsecurity=False).hexdigest() + ".json"
    (cache / name).write_text(json.dumps({"accessToken": "SECRET-TOKEN", "expiresAt": expires_at,
                                          "refreshToken": "SECRET-REFRESH"}))


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.mark.parametrize("delta,status", [(timedelta(hours=4), "ok"), (timedelta(minutes=30), "warn"),
                                          (timedelta(minutes=-5), "FAILED")])
def test_sso_remaining(tmp_path, delta, status):
    cfg = tmp_path / "config"
    cfg.write_text(CONFIG)
    cache = tmp_path / "cache"
    cache.mkdir()
    cache_file(cache, "ADRES-ORGANIZATION", iso(NOW + delta))
    c = checks.check_sso_remaining("ADR-DEV-MEDICALAUDIT", cfg, cache, NOW)
    assert c.status == status
    assert "SECRET" not in c.detail


def test_sso_remaining_skips_without_session_or_cache(tmp_path):
    cfg = tmp_path / "config"
    cfg.write_text("[profile P]\nregion = us-east-1\n")
    assert checks.check_sso_remaining("P", cfg, tmp_path, NOW).status == "skipped"
    cfg.write_text(CONFIG)
    assert checks.check_sso_remaining("ADR-DEV-MEDICALAUDIT", cfg, tmp_path, NOW).status == "skipped"


# ---- appconfig_live -----------------------------------------------------------
def test_appconfig_live_ok():
    c, live = checks.check_appconfig_live(lambda: lp())
    assert c.status == "ok" and live is not None


def test_appconfig_live_failure():
    from iae_launch.live import LiveConfigError

    def boom():
        raise LiveConfigError("sin deployment COMPLETE")
    c, live = checks.check_appconfig_live(boom)
    assert c.status == "FAILED" and live is None and "COMPLETE" in c.detail


def test_appconfig_live_in_progress():
    c, live = checks.check_appconfig_live(lambda: lp(in_progress={"api/storage": (4,)}))
    assert c.status == "FAILED" and "api/storage" in c.detail and live is not None


def test_ingest_mapping():
    assert checks.check_ingest_mapping(lp()).status == "ok"
    bad = checks.check_ingest_mapping(lp(ingest_mappings={"raw/": {}}))
    assert bad.status == "FAILED" and "staging/s/" in bad.detail
    assert checks.check_ingest_mapping(None).status == "skipped"


def test_runtime_qualifier():
    c = checks.check_runtime_qualifier(lp())
    assert c.status == "ok" and "v4_16_0" in c.detail
    assert checks.check_runtime_qualifier(None).status == "skipped"


# ---- dispatch flag ------------------------------------------------------------
def disabled():
    return lp(dispatch=Deployed("app", "env", "prof", 9, 1, {"values": {"dispatch": {"enabled": False}}}))


def test_dispatch_enabled_ok(stubbed):
    assert checks.check_dispatch_flag(stubbed("appconfig").client, lp(), False).status == "ok"


def test_dispatch_disabled_marker_warns(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_deployments", {"Items": [{"DeploymentNumber": 7, "ConfigurationName": "dispatch", "State": "COMPLETE"}]},
          ApplicationId="app", EnvironmentId="env")
    sc.ok("get_deployment", {"Description": dispatch.CLOSE_MARKER}, ApplicationId="app",
          EnvironmentId="env", DeploymentNumber=7)
    c = checks.check_dispatch_flag(sc.client, disabled(), False)
    assert c.status == "warn" and "reabrirá" in c.detail


def test_dispatch_disabled_by_operator_fails_unless_allowed(stubbed):
    for allow, status in ((False, "FAILED"), (True, "warn")):
        sc = stubbed("appconfig")
        sc.ok("list_deployments", {"Items": [{"DeploymentNumber": 7, "ConfigurationName": "dispatch", "State": "COMPLETE"}]},
              ApplicationId="app", EnvironmentId="env")
        sc.ok("get_deployment", {"Description": "manual"}, ApplicationId="app", EnvironmentId="env",
              DeploymentNumber=7)
        assert checks.check_dispatch_flag(sc.client, disabled(), allow).status == status


def test_dispatch_flag_skipped_without_live(stubbed):
    assert checks.check_dispatch_flag(stubbed("appconfig").client, None, False).status == "skipped"


def test_dispatch_strategy(stubbed):
    sc = stubbed("appconfig")
    sc.ok("list_deployment_strategies", {"Items": [
        {"Id": "s1", "Name": "adr-appconfig-seed-nobake", "DeploymentDurationInMinutes": 0,
         "FinalBakeTimeInMinutes": 0}]})
    c = checks.check_dispatch_strategy(sc.client)
    assert c.status == "ok" and "adr-appconfig-seed-nobake" in c.detail
    sc.ok("list_deployment_strategies", {"Items": [
        {"Id": "s2", "Name": "slow", "DeploymentDurationInMinutes": 5, "FinalBakeTimeInMinutes": 5}]})
    assert checks.check_dispatch_strategy(sc.client).status == "FAILED"


# ---- breadcrumb ---------------------------------------------------------------
def test_foreign_breadcrumb(tmp_path):
    assert checks.check_foreign_breadcrumb("dev", tmp_path).status == "ok"
    (tmp_path / "pipeline-runner").mkdir()
    (tmp_path / "pipeline-runner" / "paused-dev.json").write_text("{}")
    c = checks.check_foreign_breadcrumb("dev", tmp_path)
    assert c.status == "FAILED" and "paused-dev.json" in c.detail
    assert checks.check_foreign_breadcrumb("test", tmp_path).status == "ok"


# ---- executions / conveyor / bastion --------------------------------------------
def test_running_executions(stubbed):
    sf = stubbed("stepfunctions")
    sf.ok("list_executions", {"executions": []}, stateMachineArn="arn", statusFilter="RUNNING")
    assert checks.check_running_executions(sf.client, "arn").status == "ok"
    ex = {"executionArn": "e", "stateMachineArn": "arn", "name": "n", "status": "RUNNING",
          "startDate": datetime(2026, 1, 1)}
    sf.ok("list_executions", {"executions": [ex, ex]}, stateMachineArn="arn", statusFilter="RUNNING")
    c = checks.check_running_executions(sf.client, "arn")
    assert c.status == "warn" and "2" in c.detail


def test_conveyor_depth(stubbed):
    sqs = stubbed("sqs")
    sqs.ok("get_queue_attributes", {"Attributes": {"ApproximateNumberOfMessages": "7",
                                                   "ApproximateNumberOfMessagesNotVisible": "3"}},
           QueueUrl="u", AttributeNames=["ApproximateNumberOfMessages",
                                         "ApproximateNumberOfMessagesNotVisible"])
    c, depth = checks.check_conveyor_depth(sqs.client, "u")
    assert c.status == "ok" and depth == 10 and "10" in c.detail


def test_bastion_online(stubbed):
    ssm = stubbed("ssm")
    flt = [{"Key": "InstanceIds", "Values": ["i-068050b46fe0feabb"]}]
    both = lambda n: "/usr/bin/" + n
    ssm.ok("describe_instance_information",
           {"InstanceInformationList": [{"InstanceId": "i-068050b46fe0feabb", "PingStatus": "Online"}]},
           Filters=flt)
    c, host = checks.check_bastion_online(ssm.client, None, DEV, both)
    assert c.status == "ok" and host.instance_id == "i-068050b46fe0feabb" and "configurado" in c.detail
    ssm.ok("describe_instance_information",
           {"InstanceInformationList": [{"InstanceId": "i-068050b46fe0feabb", "PingStatus": "Online"}]},
           Filters=flt)
    c, host = checks.check_bastion_online(ssm.client, None, DEV, lambda n: None)
    assert c.status == "FAILED" and "session-manager-plugin" in c.detail


def test_bastion_fallback_reports_chosen_host_and_fails_if_none(stubbed):
    ssm, ec2 = stubbed("ssm"), stubbed("ec2")
    flt = [{"Key": "InstanceIds", "Values": ["i-068050b46fe0feabb"]}]
    sub = ["subnet-038ad5c2f9a8c0994"]
    ssm.ok("describe_instance_information", {"InstanceInformationList": []}, Filters=flt)
    ec2.ok("describe_subnets", {"Subnets": [{"SubnetId": sub[0], "VpcId": "vpc-1"}]}, SubnetIds=sub)
    ssm.ok("describe_instance_information", {"InstanceInformationList": [
        {"InstanceId": "i-zzz", "PingStatus": "Online"}]})
    ec2.ok("describe_instances", {"Reservations": [{"Instances": [
        {"InstanceId": "i-zzz", "VpcId": "vpc-1", "State": {"Name": "running"},
         "Tags": [{"Key": "Name", "Value": "my-bastion"}]}]}]}, InstanceIds=["i-zzz"])
    c, host = checks.check_bastion_online(ssm.client, ec2.client, DEV, lambda n: "/x/" + n)
    assert c.status == "ok" and host.instance_id == "i-zzz" and "my-bastion" in c.detail
    ssm.ok("describe_instance_information", {"InstanceInformationList": []}, Filters=flt)
    ec2.ok("describe_subnets", {"Subnets": [{"SubnetId": sub[0], "VpcId": "vpc-1"}]}, SubnetIds=sub)
    ssm.ok("describe_instance_information", {"InstanceInformationList": []})
    c, host = checks.check_bastion_online(ssm.client, ec2.client, DEV, lambda n: "/x/" + n)
    assert c.status == "FAILED" and host is None


# ---- secret / token --------------------------------------------------------------
def test_secret_present():
    assert checks.check_client_secret_present(DEV, {"IAE_CLIENT_SECRET": "x"}).status == "ok"
    c = checks.check_client_secret_present(DEV, {})
    assert c.status == "skipped" and "asm-exec" in c.detail and "adr-dev-medicalaudit-scriptconnection" in c.detail
    assert checks.check_client_secret_present(DEV, {"IAE_CLIENT_SECRET": ""}).status == "skipped"
    assert "x" != c.detail


def jwt(payload):
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'none'})}.{enc(payload)}.sig"


def test_token_audience_ok_and_reports_only_aud_exp():
    aud = envs.expected_audience("dev")
    fn = lambda spec, secret: auth.Token(jwt({"aud": [aud, "other"], "exp": 5, "sub": "PRIVATE"}))
    c, tok = checks.check_token_audience(DEV, {"IAE_CLIENT_SECRET": "s"}, fn)
    assert c.status == "ok" and tok is not None
    assert "PRIVATE" not in c.detail and "exp" in c.detail


def test_token_audience_mismatch():
    fn = lambda spec, secret: auth.Token(jwt({"aud": "account"}))
    c, tok = checks.check_token_audience(DEV, {"IAE_CLIENT_SECRET": "s"}, fn)
    assert c.status == "FAILED" and "account" in c.detail and tok is None


def test_token_audience_skipped_without_secret():
    c, tok = checks.check_token_audience(DEV, {}, lambda *a: None)
    assert c.status == "skipped" and tok is None


def test_token_auth_error_does_not_leak_secret():
    def fn(spec, secret):
        raise auth.AuthError("Keycloak respondió HTTP 401")
    c, _ = checks.check_token_audience(DEV, {"IAE_CLIENT_SECRET": "TOPSECRET"}, fn)
    assert c.status == "FAILED" and "TOPSECRET" not in c.detail


# ---- api probe ----------------------------------------------------------------------
@pytest.mark.parametrize("status,expected", [(404, "ok"), (401, "FAILED"), (403, "FAILED"), (500, "warn")])
def test_api_probe(status, expected):
    c = checks.check_api_probe(lambda: status)
    assert c.status == expected


def test_api_probe_skipped_when_not_requested():
    assert checks.check_api_probe(None).status == "skipped"


def test_secret_missing_and_no_working_asm_exec(monkeypatch):
    monkeypatch.setattr(envs, "resolve_asm_exec", lambda: None)
    c = checks.check_client_secret_present(DEV, {})
    assert c.status == "skipped" and "no hay un asm-exec funcional" in c.detail


def test_dispatch_flag_reports_max_messages_per_cycle(stubbed):
    d = Deployed("app", "env", "prof", 9, 1, {"values": {"dispatch": {"enabled": True, "maxMessagesPerCycle": 10}}})
    c = checks.check_dispatch_flag(stubbed("appconfig").client, lp(dispatch=d), False, n_claims=25)
    assert c.status == "ok" and "maxMessagesPerCycle=10" in c.detail and "3 ciclos" in c.detail
    c = checks.check_dispatch_flag(stubbed("appconfig").client, lp(dispatch=d), False, n_claims=5)
    assert "maxMessagesPerCycle=10" in c.detail and "ciclos" not in c.detail


RT = "adr_test_medicalaudit_intelligent_audit_engine"


def _agentcore(stubbed, endpoints):
    ac = stubbed("bedrock-agentcore-control")
    ac.ok("list_agent_runtimes", {"agentRuntimes": [
        {"agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/other", "agentRuntimeId": "r0",
         "agentRuntimeVersion": "1", "agentRuntimeName": RT + "_copy", "description": "d", "lastUpdatedAt": 0, "status": "READY"},
        {"agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/r1", "agentRuntimeId": "r1",
         "agentRuntimeVersion": "1", "agentRuntimeName": RT, "description": "d", "lastUpdatedAt": 0, "status": "READY"}]})
    ac.ok("list_agent_runtime_endpoints", {"runtimeEndpoints": [
        {"name": n, "status": st, "agentRuntimeEndpointArn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:e/" + n,
         "agentRuntimeArn": "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/r1", "id": n,
         "createdAt": 0, "lastUpdatedAt": 0} for n, st in endpoints]}, agentRuntimeId="r1")
    return ac


def test_runtime_qualifier_endpoint_ready_and_newest(stubbed):
    ac = _agentcore(stubbed, [("v4_15_0", "READY"), ("v4_16_0", "READY"), ("DEFAULT", "READY")])
    c = checks.check_runtime_qualifier(lp(), ac.client, "test")
    assert c.status == "ok" and "v4_16_0" in c.detail and "READY" in c.detail


def test_runtime_qualifier_warns_when_not_newest(stubbed):
    ac = _agentcore(stubbed, [("v4_16_0", "READY"), ("v4_17_0", "READY")])
    c = checks.check_runtime_qualifier(lp(), ac.client, "test")
    assert c.status == "warn" and "v4_17_0" in c.detail


def test_runtime_qualifier_missing_or_not_ready(stubbed):
    c = checks.check_runtime_qualifier(lp(), _agentcore(stubbed, [("v4_15_0", "READY")]).client, "test")
    assert c.status == "FAILED" and "no existe" in c.detail
    c = checks.check_runtime_qualifier(lp(), _agentcore(stubbed, [("v4_16_0", "CREATING")]).client, "test")
    assert c.status == "FAILED" and "CREATING" in c.detail
