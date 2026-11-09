"""Stubbed boto3 clients: any call a test did not script fails the test.

That is the point for a tool whose safety story is "the dry run writes nothing":
an unexpected PutItem/SendMessageBatch surfaces as a StubResponseError instead of
passing silently.
"""

from __future__ import annotations

import io
import json
from collections.abc import Callable, Iterator

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import Stubber


@pytest.fixture
def stubbed() -> Iterator[Callable[[str], tuple[object, Stubber]]]:
    stubbers: list[Stubber] = []

    def make(service: str) -> tuple[object, Stubber]:
        client = boto3.client(
            service,
            region_name="us-east-1",
            aws_access_key_id="testing",
            aws_secret_access_key="testing",
        )
        stub = Stubber(client)
        stub.activate()
        stubbers.append(stub)
        return client, stub

    yield make
    for stub in stubbers:
        stub.assert_no_pending_responses()
        stub.deactivate()


def body(payload: dict | bytes) -> StreamingBody:
    """An S3 GetObject Body for a stubbed response."""
    raw = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return StreamingBody(io.BytesIO(raw), len(raw))
