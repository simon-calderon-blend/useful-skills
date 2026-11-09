import json
from datetime import datetime, timezone

from iae_launch import auth, claims, envs, runner
from iae_launch.live import LiveConfigError
from tests.test_live import fake_loader

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
SM_ARN = "arn:aws:states:us-east-1:072055531089:stateMachine:adr-dev-medicalaudit-pipeline"

CONFIG = "[profile ADR-DEV-MEDICALAUDIT]\nsso_session = S\n\n[sso-session S]\nsso_start_url = x\n"


def base_kw(tmp_path, **over):
    cfg = tmp_path / "config"
    cfg.write_text(CONFIG)
    cache = tmp_path / "sso"
    cache.mkdir()
    kw = dict(environ={}, config_path=cfg, sso_cache=cache, state_home=tmp_path / "state", now=NOW,
              which=lambda n: "/bin/" + n, loader=fake_loader(), token_fn=None, probe_factory=None)
    kw.update(over)
    return kw


def stub_infra(stubbed):
    c = {k: stubbed(k) for k in ("sts", "appconfig", "apigateway", "stepfunctions", "s3", "sqs", "ssm")}
    c["sts"].ok("get_caller_identity", {"Account": "072055531089", "Arn": "arn:aws:iam::123456789012:user/x",
                                         "UserId": "u"})
    c["apigateway"].ok("get_rest_apis", {"items": [{"id": "abc", "name": "adr-dev-medicalaudit-api-gateway"}]})
    c["apigateway"].ok("get_stages", {"item": [{"stageName": "v1"}]}, restApiId="abc")
    c["stepfunctions"].ok("list_state_machines", {"stateMachines": [
        {"name": "adr-dev-medicalaudit-pipeline", "stateMachineArn": SM_ARN, "type": "STANDARD",
         "creationDate": 0}]})
    c["s3"].ok("head_bucket", {}, Bucket="adr-dev-medicalaudit-workarea")
    c["sqs"].ok("get_queue_url", {"QueueUrl": "https://q"},
                QueueName="adr-dev-medicalaudit-doc-extraction-chunks-conveyor")
    c["appconfig"].ok("list_deployment_strategies", {"Items": [
        {"Id": "s1", "Name": "adr-appconfig-seed-nobake", "DeploymentDurationInMinutes": 0,
         "FinalBakeTimeInMinutes": 0}]})
    c["stepfunctions"].ok("list_executions", {"executions": []}, stateMachineArn=SM_ARN,
                          statusFilter="RUNNING")
    c["sqs"].ok("get_queue_attributes", {"Attributes": {"ApproximateNumberOfMessages": "0",
                                                         "ApproximateNumberOfMessagesNotVisible": "0"}},
                QueueUrl="https://q", AttributeNames=["ApproximateNumberOfMessages",
                                                      "ApproximateNumberOfMessagesNotVisible"])
    c["ssm"].ok("describe_instance_information",
                {"InstanceInformationList": [{"InstanceId": "i-068050b46fe0feabb", "PingStatus": "Online"}]},
                Filters=[{"Key": "InstanceIds", "Values": ["i-068050b46fe0feabb"]}])
    return runner.Clients(**{k: v.client for k, v in c.items()})


def names(res):
    return {c.name: c.status for c in res.report.checks}


def test_sensitive_profile_short_circuits(tmp_path):
    inp = runner.Inputs(env="dev", profile="ADR-PROD-X")
    res = runner.run_preflight(inp, runner.Clients(), **base_kw(tmp_path))
    assert names(res) == {"profile_not_sensitive": "FAILED"}


def test_missing_profile_short_circuits(tmp_path):
    inp = runner.Inputs(env="dev", profile="ADRES-TEST-MEDICAL-AUDIT-1")
    res = runner.run_preflight(inp, runner.Clients(), **base_kw(tmp_path))
    assert names(res) == {"profile_not_sensitive": "ok", "profile_in_aws_config": "FAILED"}


def test_env_level_happy_path(stubbed, tmp_path):
    clients = stub_infra(stubbed)
    res = runner.run_preflight(runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT"), clients,
                               **base_kw(tmp_path))
    st = names(res)
    assert st["aws_identity"] == "ok" and st["appconfig_live"] == "ok"
    assert st["dispatch_flag"] == "ok" and st["runtime_qualifier"] == "ok"
    assert st["client_secret_present"] == "skipped" and st["token_audience"] == "skipped"
    assert st["api_probe"] == "skipped" and st["conveyor_depth"] == "ok"
    assert "claims_exist" not in st
    assert res.report.ok
    assert res.resolved.api_base_url == "https://abc.execute-api.us-east-1.amazonaws.com/v1"
    assert res.resolved.state_machine_arn == SM_ARN and res.resolved.bucket == "adr-dev-medicalaudit-workarea"
    assert res.resolved.live.qualifier == "v4_16_0" and res.resolved.conveyor_depth == 0


def test_appconfig_failure_skips_dependents_but_continues(stubbed, tmp_path):
    clients = stub_infra(stubbed)

    def bad_loader(app, profile):
        raise LiveConfigError("sin COMPLETE")
    res = runner.run_preflight(runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT"), clients,
                               **base_kw(tmp_path, loader=bad_loader))
    st = names(res)
    assert st["appconfig_live"] == "FAILED" and st["dispatch_flag"] == "skipped"
    assert st["runtime_qualifier"] == "skipped" and st["conveyor_depth"] == "ok"
    assert not res.report.ok


def make_claim(root, name, files):
    raw = root / name / claims.RAW_DIR
    raw.mkdir(parents=True)
    for f, content in files.items():
        (raw / f).write_text(content if isinstance(content, str) else json.dumps(content))


def test_claim_level_checks(stubbed, tmp_path):
    clients = stub_infra(stubbed)
    src = tmp_path / "src"
    make_claim(src, "0001_100", {"FAC_1.pdf": "x", "claim_invoice_details.json": {"detalles": [{"a": 1}]}})
    inp = runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_dir=src, claims=["0001_100"])
    res = runner.run_preflight(inp, clients, **base_kw(tmp_path))
    st = names(res)
    for n in ("claims_exist", "claim_id_parses", "prerequisite_globs", "large_pdfs", "tracker_duplicates",
              "request_json_override", "invoice_details", "structuring_source", "count_throttle",
              "batch_gate_estimate"):
        assert n in st, n
    assert st["claims_exist"] == "ok" and st["invoice_details"] == "ok"
    assert st["tracker_duplicates"] == "skipped"          # dev
    assert st["batch_gate_estimate"] == "warn"              # 8 < 100
    assert res.fields_by_claim["0001_100"]["idReclamacion"] == 100


def test_missing_claim_skips_dependents(stubbed, tmp_path):
    clients = stub_infra(stubbed)
    src = tmp_path / "src"
    src.mkdir()
    inp = runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_dir=src, claims=["0001_100"])
    res = runner.run_preflight(inp, clients, **base_kw(tmp_path))
    st = names(res)
    assert st["claims_exist"] == "FAILED" and "invoice_details" not in st


def test_token_audience_and_probe(stubbed, tmp_path):
    import base64
    clients = stub_infra(stubbed)
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    tok = auth.Token(f"{enc({})}.{enc({'aud': envs.expected_audience('dev'), 'exp': 1})}.s")
    seen = {}

    def probe_factory(resolved, token):
        seen["token"] = token
        return lambda: 404
    kw = base_kw(tmp_path, environ={"IAE_CLIENT_SECRET": "s"}, token_fn=lambda spec, secret: tok,
                 probe_factory=probe_factory)
    res = runner.run_preflight(runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", probe_api=True),
                               clients, **kw)
    st = names(res)
    assert st["token_audience"] == "ok" and st["api_probe"] == "ok" and seen["token"] is tok


def test_probe_requested_without_token(stubbed, tmp_path):
    clients = stub_infra(stubbed)
    res = runner.run_preflight(runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", probe_api=True),
                               clients, **base_kw(tmp_path))
    assert names(res)["api_probe"] == "skipped"
    assert "token" in [c for c in res.report.checks if c.name == "api_probe"][0].detail


def test_clients_lazy_session():
    made = []

    class Sess:
        def client(self, name, region_name=None):
            made.append((name, region_name))
            return object()
    c = runner.Clients(Sess())
    assert c["sts"] is c["sts"] and made == [("sts", "us-east-1")]


def test_index_mode_preflight_wires_ddb_request_mode_and_deliverability(stubbed, tmp_path, monkeypatch):
    from iae_launch import sourceindex as si
    from tests.test_source_mode import REQ, source
    clients = stub_infra(stubbed)
    clients._cache["dynamodb"] = object()
    seen = {}
    sc = source(req=dict(REQ, nitEntidad="890981726"))
    sc.request_pid = "22222222-2222-4222-8222-222222222222"
    sc.request_body["soportes"]["rutaArchivosSoportes"] = "https://h.example.com/o/890981726/1072/a/"
    monkeypatch.setattr(si, "read_index", lambda path, bucket, base, only=None: [sc.row])

    def fake_load(s3, bucket, live, row, **kw):
        seen.update(kw)
        return sc
    monkeypatch.setattr(si, "load_source", fake_load)
    inp = runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_index="i.csv", structuring="workarea",
                        request="source", invoice="lambda", skip_delivery=False)
    res = runner.run_preflight(inp, clients, **base_kw(tmp_path))
    assert seen["request_mode"] == "source" and seen["require_deliverable"] is True and seen["ddb"] is not None
    assert names(res)["request_deliverable"] == "ok" and res.sources["0001_5"].request_pid.startswith("2222")
    assert res.fields_by_claim["0001_5"] == {"idReclamacion": 5}


def test_dir_mode_api_request_fails_deliverability(stubbed, tmp_path):
    clients = stub_infra(stubbed)
    src = tmp_path / "src"
    make_claim(src, "0001_100", {"FAC_1.pdf": "x"})
    inp = runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_dir=src, claims=["0001_100"],
                        invoice="lambda")
    res = runner.run_preflight(inp, clients, **base_kw(tmp_path))
    check = [c for c in res.report.checks if c.name == "request_deliverable"][0]
    assert check.status == "FAILED" and "SIEMPRE falla" in check.detail
    inp.skip_delivery = True
    clients = stub_infra(stubbed)
    (tmp_path / "b").mkdir()
    res = runner.run_preflight(inp, clients, **base_kw(tmp_path / "b"))
    assert names(res)["request_deliverable"] == "warn"


def test_dir_mode_local_request_is_read(stubbed, tmp_path):
    clients = stub_infra(stubbed)
    src = tmp_path / "src"
    good = {"idReclamacion": 100, "idSolicitud": 100, "nitEntidad": "9",
            "soportes": {"rutaArchivosObligatorios": "a", "rutaArchivosSoportes": "https://h.example.com/o/9/12/x/"}}
    make_claim(src, "0001_100", {"FAC_1.pdf": "x", "request.json": good})
    inp = runner.Inputs(env="dev", profile="ADR-DEV-MEDICALAUDIT", source_dir=src, claims=["0001_100"],
                        request="local", invoice="lambda")
    assert names(runner.run_preflight(inp, clients, **base_kw(tmp_path)))["request_deliverable"] == "ok"
