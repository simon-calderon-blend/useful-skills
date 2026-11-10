"""End-to-end through main() with every AWS client stubbed.

Unscripted calls raise, so "dry run writes nothing" is checked by construction:
the dry-run tests script reads only.
"""

import json
from datetime import datetime, timezone

import pytest
from botocore.exceptions import TokenRetrievalError

from padding_gate.cli import main
from tests.conftest import body

ENV = "test"
ACCOUNT = "276553701208"
APP = "adr-test-medicalaudit-doc-extraction-appconfig"
TABLE = "adr-test-medicalaudit-doc-extraction-chunks"
BUCKET = "adr-test-medicalaudit-workarea"
QUEUE = f"https://sqs.us-east-1.amazonaws.com/{ACCOUNT}/adr-test-medicalaudit-doc-extraction-chunks-conveyor"
DIGEST = "c" * 64
MODEL = f"arn:aws:bedrock:us-east-1:{ACCOUNT}:application-inference-profile/x"
JOB = f"arn:aws:bedrock:us-east-1:{ACCOUNT}:model-invocation-job/j1"
RUN = "0123456789ab"
SERVICES = ("sts", "appconfig", "sqs", "dynamodb", "s3", "bedrock")


class FakeSession:
    def __init__(self, clients):
        self._clients = clients

    def client(self, name, **_):
        return self._clients[name]


@pytest.fixture
def aws(stubbed):
    made = {name: stubbed(name) for name in SERVICES}
    clients = {name: pair[0] for name, pair in made.items()}
    stubs = {name: pair[1] for name, pair in made.items()}
    calls = []

    def factory(**kwargs):
        calls.append(kwargs)
        return FakeSession(clients)

    return stubs, factory, calls


def _identity(stubs, account=ACCOUNT):
    stubs["sts"].add_response(
        "get_caller_identity",
        {"Account": account, "Arn": f"arn:aws:sts::{account}:assumed-role/r/u", "UserId": "u"},
    )


def _live_config(stubs):
    s = stubs["appconfig"]
    s.add_response("list_applications", {"Items": [{"Id": "app", "Name": APP}]})
    s.add_response("list_environments", {"Items": [{"ApplicationId": "app", "Id": "env", "Name": ENV}]})
    s.add_response("list_configuration_profiles", {"Items": [
        {"ApplicationId": "app", "Id": f"p-{n}", "Name": n} for n in ("batch", "storage", "extraction")
    ]})
    s.add_response("list_deployments", {"Items": [
        {"DeploymentNumber": 3, "ConfigurationName": "extraction", "ConfigurationVersion": "1", "State": "COMPLETE"},
        {"DeploymentNumber": 2, "ConfigurationName": "storage", "ConfigurationVersion": "1", "State": "COMPLETE"},
        {"DeploymentNumber": 1, "ConfigurationName": "batch", "ConfigurationVersion": "1", "State": "COMPLETE"},
    ]})
    for payload in (
        {"min_records_per_job": 100},
        {"work": {"run_configs": "_global/run-configs/",
                  "run_config_pointers": "staging/document-extraction/run-config/"}},
        {"extractable_doc_codes": ["ADM", "PDX"], "always_ondemand_doc_codes": ["FAC"]},
    ):
        s.add_response("get_hosted_configuration_version", {"Content": json.dumps(payload).encode()})


def _queue(stubs, *depths):
    stubs["sqs"].add_response("get_queue_url", {"QueueUrl": QUEUE})
    for visible in depths:
        stubs["sqs"].add_response("get_queue_attributes", {"Attributes": {
            "ApproximateNumberOfMessages": str(visible), "ApproximateNumberOfMessagesNotVisible": "0"}})


def _pending_real_chunks(stubs, n):
    stubs["dynamodb"].add_response("scan", {"Items": [
        {"chunk_id": {"S": f"01JREAL{i}"}, "pdf_id": {"S": "pdf-1"}, "process_id": {"S": "proc-1"},
         "run_id": {"S": "proc-1-1"}, "doc_code": {"S": "ADM"}}
        for i in range(n)
    ]})
    stubs["s3"].add_response("get_object", {"Body": body({"config_digest": DIGEST})})
    stubs["s3"].add_response("get_object", {"Body": body(
        {"model": {"model_id": MODEL}, "documents": {"ADM": {}, "PDX": {}}})})


def _base_args(command):
    return [command, "--env", ENV, "--profile", "ADR-TEST-MEDICALAUDIT"]


def test_sensitive_profile_is_refused_before_any_session(aws, capsys):
    _, factory, calls = aws
    code = main(["status", "--env", ENV, "--profile", "ADR-PROD-MEDICALAUDIT-RO"], session_factory=factory)
    assert code == 2
    assert calls == []
    assert "sensitive" in capsys.readouterr().err


def test_profile_of_another_account_is_refused(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs, account="072055531089")
    assert main(_base_args("status"), session_factory=factory) == 2
    assert "072055531089" in capsys.readouterr().err


def test_status_json_recommends_the_top_up(aws, capsys):
    stubs, factory, calls = aws
    _identity(stubs)
    _live_config(stubs)
    _queue(stubs, 30)
    _pending_real_chunks(stubs, 30)
    stubs["dynamodb"].add_response("scan", {"Items": []})  # no filler runs

    assert main(_base_args("status") + ["--json"], session_factory=factory) == 0

    report = json.loads(capsys.readouterr().out)
    assert calls == [{"profile_name": "ADR-TEST-MEDICALAUDIT", "region_name": "us-east-1"}]
    assert report["min_records"] == 100
    assert report["queue"] == {"visible": 30, "inflight": 0}
    assert report["groups"][0]["model_id"] == MODEL
    assert report["recommendation"]["count"] == 80
    assert report["spuria_runs"] == []


def test_inject_dry_run_writes_nothing(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _queue(stubs, 30)
    _pending_real_chunks(stubs, 30)

    assert main(_base_args("inject"), session_factory=factory) == 0

    out = capsys.readouterr().out
    assert "DRY-RUN" in out
    assert "count:" in out and "80" in out


def test_inject_apply_waits_writes_and_prints_the_run_id(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _queue(stubs, 95, 95)  # quiet check, snapshot
    _pending_real_chunks(stubs, 95)
    stubs["s3"].add_response("put_object", {})
    stubs["s3"].add_response("put_object", {})
    for _ in range(15):
        stubs["dynamodb"].add_response("put_item", {})
    for _ in range(2):
        stubs["sqs"].add_response("send_message_batch", {"Successful": [], "Failed": []})
    stubs["sqs"].add_response("get_queue_attributes", {"Attributes": {  # depth after the write
        "ApproximateNumberOfMessages": "110", "ApproximateNumberOfMessagesNotVisible": "0"}})
    code = main(
        _base_args("inject") + ["--apply", "--json", "--quiet-seconds", "0"],
        session_factory=factory, sleep=lambda _: None,
    )

    assert code == 0
    report = json.loads(capsys.readouterr().out)
    assert report["count"] == 15
    assert len(report["run_id"]) == 12
    assert report["cleanup_command"].endswith(f"cleanup --env {ENV} --profile ADR-TEST-MEDICALAUDIT "
                                              f"--run-id {report['run_id']} --apply")


def test_inject_refusal_exits_2(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _queue(stubs, 0)
    stubs["dynamodb"].add_response("scan", {"Items": []})

    assert main(_base_args("inject"), session_factory=factory) == 2
    assert "empty" in capsys.readouterr().err


def test_cleanup_apply_is_refused_while_the_job_runs(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    stubs["dynamodb"].add_response("scan", {"Items": [
        {"chunk_id": {"S": f"spuria{RUN}x"}, "spuria_run_id": {"S": RUN},
         "status": {"S": "IN_BATCH"}, "batch_job_id": {"S": JOB}},
    ]})
    stubs["bedrock"].add_response("get_model_invocation_job", {
        "jobArn": JOB, "modelId": "m", "roleArn": f"arn:aws:iam::{ACCOUNT}:role/r",
        "submitTime": datetime(2026, 11, 9, tzinfo=timezone.utc),
        "inputDataConfig": {"s3InputDataConfig": {"s3Uri": "s3://b/i/"}},
        "outputDataConfig": {"s3OutputDataConfig": {"s3Uri": "s3://b/o/"}},
        "status": "InProgress",
    })

    assert main(_base_args("cleanup") + ["--run-id", RUN, "--apply"], session_factory=factory) == 2
    captured = capsys.readouterr()
    assert "InProgress" in captured.out + captured.err


def test_expired_sso_token_points_at_awsl(aws, capsys):
    stubs, factory, _ = aws
    stubs["sts"].add_client_error("get_caller_identity", service_error_code="ExpiredToken")
    assert main(_base_args("status"), session_factory=factory) == 3
    assert "awsl" in capsys.readouterr().err


def test_token_retrieval_error_points_at_awsl(capsys):
    def factory(**_):
        raise TokenRetrievalError(provider="sso", error_msg="expired")

    assert main(_base_args("status"), session_factory=factory) == 3
    assert "awsl" in capsys.readouterr().err


def _safe_run_rows(stubs):
    stubs["dynamodb"].add_response("scan", {"Items": [
        {"chunk_id": {"S": f"spuria{RUN}a"}, "spuria_run_id": {"S": RUN}, "status": {"S": "DONE"}},
    ]})


def test_inject_dry_run_does_not_promise_a_run_id(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _queue(stubs, 30)
    _pending_real_chunks(stubs, 30)
    assert main(_base_args("inject"), session_factory=factory) == 0
    out = capsys.readouterr().out
    assert "assigned at --apply" in out


def test_cleanup_dry_run_on_a_safe_run_writes_nothing(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _safe_run_rows(stubs)
    assert main(_base_args("cleanup") + ["--run-id", RUN], session_factory=factory) == 0
    assert "Safe to re-run with --apply" in capsys.readouterr().out


def test_cleanup_dry_run_on_a_blocked_run_exits_2(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    stubs["dynamodb"].add_response("scan", {"Items": [
        {"chunk_id": {"S": f"spuria{RUN}a"}, "spuria_run_id": {"S": RUN}, "status": {"S": "PENDING"}},
    ]})
    assert main(_base_args("cleanup") + ["--run-id", RUN], session_factory=factory) == 2
    assert "blocked" in capsys.readouterr().out


def test_cleanup_apply_deletes_rows_then_prefix(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _safe_run_rows(stubs)
    stubs["dynamodb"].add_response("delete_item", {})
    key = f"audit-processes/spuria-{RUN}/chunks/blank.pdf"
    stubs["s3"].add_response("list_objects_v2", {"Contents": [{"Key": key}]})
    stubs["s3"].add_response("delete_objects", {})

    assert main(_base_args("cleanup") + ["--run-id", RUN, "--apply"], session_factory=factory) == 0
    assert "deleted 1 row(s) and 1 S3 object(s)" in capsys.readouterr().out


def test_cleanup_abandon_pending_removes_rows_that_never_formed_a_job(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    stubs["dynamodb"].add_response("scan", {"Items": [
        {"chunk_id": {"S": f"spuria{RUN}a"}, "spuria_run_id": {"S": RUN}, "status": {"S": "PENDING"}},
    ]})
    stubs["dynamodb"].add_response("delete_item", {})
    stubs["s3"].add_response("list_objects_v2", {})

    code = main(_base_args("cleanup") + ["--run-id", RUN, "--abandon-pending", "--apply"],
                session_factory=factory)
    assert code == 0


def test_endpoint_override_is_refused(aws, capsys, monkeypatch):
    _, factory, calls = aws
    monkeypatch.setenv("AWS_ENDPOINT_URL_SQS", "http://localhost:4566")
    assert main(_base_args("status"), session_factory=factory) == 2
    assert calls == []


def test_expired_token_mid_inject_keeps_the_awsl_hint_and_the_run_id(aws, capsys):
    stubs, factory, _ = aws
    _identity(stubs)
    _live_config(stubs)
    _queue(stubs, 95, 95)
    _pending_real_chunks(stubs, 95)
    stubs["s3"].add_client_error("put_object", service_error_code="ExpiredToken")

    code = main(_base_args("inject") + ["--apply", "--quiet-seconds", "0"],
                session_factory=factory, sleep=lambda _: None)

    err = capsys.readouterr().err
    assert code == 3
    assert "awsl" in err and "--abandon-pending" in err
