import base64
import json
import urllib.error
import urllib.parse

import pytest

from iae_launch import auth, envs


def jwt(payload: dict) -> str:
    enc = lambda d: base64.urlsafe_b64encode(json.dumps(d).encode()).rstrip(b"=").decode()
    return f"{enc({'alg': 'none'})}.{enc(payload)}.sig"


class Resp:
    def __init__(self, body):
        self._b = body

    def read(self):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_get_token_posts_client_credentials_form():
    seen = {}

    def opener(req, timeout):
        seen["url"], seen["data"], seen["timeout"] = req.full_url, req.data, timeout
        seen["method"] = req.get_method()
        return Resp(json.dumps({"access_token": "TKN"}).encode())

    tok = auth.get_token(envs.get_env("dev"), "s3cr3t", opener=opener)
    form = urllib.parse.parse_qs(seen["data"].decode())
    assert form == {"grant_type": ["client_credentials"], "client_id": ["adr-dev-medicalaudit-radicador"],
                    "client_secret": ["s3cr3t"]}
    assert seen["url"] == envs.TOKEN_URL and seen["timeout"] == 15 and seen["method"] == "POST"
    assert tok.value == "TKN"


def test_token_never_leaks_in_repr_or_str():
    tok = auth.Token("super-secret-token")
    assert "super-secret-token" not in repr(tok)
    assert "super-secret-token" not in str(tok)
    assert "super-secret-token" not in f"{tok}"


def test_http_error_has_no_secret():
    def opener(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    with pytest.raises(auth.AuthError) as ei:
        auth.get_token(envs.get_env("dev"), "s3cr3t", opener=opener)
    assert "401" in str(ei.value) and "s3cr3t" not in str(ei.value)


def test_missing_access_token():
    with pytest.raises(auth.AuthError, match="access_token"):
        auth.get_token(envs.get_env("dev"), "x", opener=lambda r, timeout: Resp(b"{}"))


def test_network_error():
    def opener(req, timeout):
        raise urllib.error.URLError("dns")
    with pytest.raises(auth.AuthError, match="red"):
        auth.get_token(envs.get_env("dev"), "x", opener=opener)


def test_decode_claims_and_audience():
    t = auth.Token(jwt({"aud": "a", "exp": 123, "secret_stuff": "no"}))
    claims = auth.decode_claims(t)
    assert claims["aud"] == "a"
    assert auth.audiences(claims) == ["a"]
    assert auth.audiences({"aud": ["x", "y"]}) == ["x", "y"]
    assert auth.audiences({}) == []


def test_decode_bad_token():
    with pytest.raises(auth.AuthError):
        auth.decode_claims(auth.Token("nope"))
