import json

import pytest

from iae_launch import api, auth


class FakeResp:
    def __init__(self, status, body):
        self.status, self._b = status, body

    def read(self):
        return self._b


class FakeConn:
    last = None

    def __init__(self, status=200, body=b"{}"):
        self.status, self.body, self.closed, self.req = status, body, False, None

    def request(self, method, path, body=None, headers=None):
        self.req = (method, path, body, headers)

    def getresponse(self):
        return FakeResp(self.status, self.body)

    def close(self):
        self.closed = True


def factory(conn):
    def make(host, port, timeout):
        make.args = (host, port, timeout)
        return conn
    return make


PID1 = "01a15f24-3ab6-72a1-96d4-f11dca711b43"
BASE = "https://abc.execute-api.us-east-1.amazonaws.com/v1"
TOK = auth.Token("TKN")


def test_post_iniciar_recibido():
    conn = FakeConn(200, json.dumps({"idProcessIA": PID1, "estado": "RECIBIDO", "mensaje": "ok"}).encode())
    f = factory(conn)
    r = api.post_iniciar(f, BASE, TOK, {"idReclamacion": 1})
    assert r.accepted and r.process_id == PID1
    assert f.args == ("abc.execute-api.us-east-1.amazonaws.com", 443, 30)
    method, path, body, headers = conn.req
    assert (method, path) == ("POST", "/v1/iniciar")
    assert json.loads(body) == {"idReclamacion": 1}
    assert headers["Authorization"] == "Bearer TKN" and headers["Content-Type"] == "application/json"
    assert conn.closed


def test_post_iniciar_rejection_keeps_existing_pid():
    body = {"idProcessIA": "old", "estado": "ERROR", "mensaje": "Ya existe un proceso activo"}
    r = api.post_iniciar(factory(FakeConn(200, json.dumps(body).encode())), BASE, TOK, {})
    assert not r.accepted and r.process_id == "old" and "Ya existe" in r.mensaje


def test_post_iniciar_http_error_truncates_body():
    with pytest.raises(api.ApiError) as ei:
        api.post_iniciar(factory(FakeConn(400, b"x" * 900)), BASE, TOK, {})
    assert ei.value.status == 400 and len(ei.value.body) == 500
    assert "TKN" not in str(ei.value)


def test_post_iniciar_non_json():
    with pytest.raises(api.ApiError, match="JSON"):
        api.post_iniciar(factory(FakeConn(200, b"<html>")), BASE, TOK, {})


def test_probe_returns_status_without_raising():
    conn = FakeConn(404, b"{}")
    assert api.probe_proceso(factory(conn), BASE, TOK, "uuid-1") == 404
    assert conn.req[0:2] == ("GET", "/v1/proceso/uuid-1")


def test_recibido_with_invalid_pid_is_bad_response():
    for bad in ("not-a-uuid", "", None, 5):
        body = json.dumps({"idProcessIA": bad, "estado": "RECIBIDO", "mensaje": "ok"}).encode()
        r = api.post_iniciar(factory(FakeConn(200, body)), BASE, TOK, {})
        assert not r.accepted and r.bad_response
