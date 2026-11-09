import io
import json

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber

REGION = "us-east-1"


def stream(doc) -> StreamingBody:
    raw = doc if isinstance(doc, bytes) else json.dumps(doc).encode()
    return StreamingBody(io.BytesIO(raw), len(raw))


class Stubbed:
    """Cliente boto3 con credenciales falsas + Stubber activado."""

    def __init__(self, service: str):
        self.client = boto3.client(service, region_name=REGION,
                                   aws_access_key_id="x", aws_secret_access_key="y")
        self.stub = Stubber(self.client)
        self.stub.activate()

    def ok(self, op, resp=None, **params):
        self.stub.add_response(op, resp or {}, params or None)
        return self

    def err(self, op, code, message="boom", **params):
        self.stub.add_client_error(op, service_error_code=code, service_message=message,
                                   expected_params=params or None)
        return self

    def done(self):
        self.stub.assert_no_pending_responses()


@pytest.fixture
def stubbed():
    made = []

    def make(service):
        s = Stubbed(service)
        made.append(s)
        return s

    yield make
    for s in made:
        s.done()


@pytest.fixture(autouse=True)
def _fixed_asm_exec(monkeypatch):
    """Determinista: ningún test depende del asm-exec instalado en la máquina."""
    from iae_launch import envs
    monkeypatch.setattr(envs, "resolve_asm_exec", lambda: ["asm-exec"])
