import signal

import pytest

from iae_launch import tunnel


class FakeProc:
    def __init__(self, pid=4242, exit_code=None, hang=False):
        self.pid, self._code, self.waited, self.hang = pid, exit_code, False, hang

    def poll(self):
        return self._code

    def wait(self, timeout=None):
        if self.hang and not self.waited:
            self.waited = True
            raise tunnel.subprocess.TimeoutExpired('aws', timeout)
        self.waited = True


def make_spawn(log_text="Starting session with SessionId: sess-123\n", proc=None):
    calls = {}

    def spawn(argv, log_path):
        calls["argv"] = argv
        log_path.write_text(log_text)
        return proc or FakeProc()
    spawn.calls = calls
    return spawn


def test_open_tunnel_builds_command_and_returns_when_port_opens(stubbed, tmp_path):
    ssm = stubbed("ssm")
    killed = []
    ssm.ok("terminate_session", {}, SessionId="sess-123")
    spawn = make_spawn()
    with tunnel.open_tunnel(profile="P", bastion="i-1", host="h.example", region="us-east-1", ssm=ssm.client,
                            local_port=9999, spawn=spawn, probe=lambda p: True,
                            kill_group=lambda pid, sig=None: killed.append(pid), log_dir=tmp_path) as t:
        assert t.local_port == 9999 and t.session_id == "sess-123"
    argv = spawn.calls["argv"]
    assert argv[:3] == ["aws", "ssm", "start-session"]
    assert argv[argv.index("--profile") + 1] == "P"
    assert argv[argv.index("--target") + 1] == "i-1"
    assert argv[argv.index("--document-name") + 1] == "AWS-StartPortForwardingSessionToRemoteHost"
    import json
    params = json.loads(argv[argv.index("--parameters") + 1])
    assert params == {"host": ["h.example"], "portNumber": ["443"], "localPortNumber": ["9999"]}
    assert killed == [4242]


def test_close_terminates_session_even_if_body_raises(stubbed, tmp_path):
    ssm = stubbed("ssm")
    ssm.ok("terminate_session", {}, SessionId="sess-123")
    killed = []
    with pytest.raises(RuntimeError):
        with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client,
                                local_port=1, spawn=make_spawn(), probe=lambda p: True,
                                kill_group=lambda pid, sig=None: killed.append(pid), log_dir=tmp_path):
            raise RuntimeError("x")
    assert killed == [4242]


def test_terminate_failure_does_not_mask(stubbed, tmp_path):
    ssm = stubbed("ssm")
    ssm.err("terminate_session", "AccessDenied", SessionId="sess-123")
    with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=1,
                            spawn=make_spawn(), probe=lambda p: True, kill_group=lambda pid, sig=None: None,
                            log_dir=tmp_path):
        pass


def test_process_exits_before_port_opens(stubbed, tmp_path):
    ssm = stubbed("ssm")
    with pytest.raises(tunnel.TunnelError, match="terminó antes"):
        with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=1,
                                spawn=make_spawn("TargetNotConnected", FakeProc(exit_code=254)),
                                probe=lambda p: False, kill_group=lambda pid, sig=None: None, log_dir=tmp_path):
            pass


def test_timeout_kills_and_terminates(stubbed, tmp_path):
    ssm = stubbed("ssm")
    ssm.ok("terminate_session", {}, SessionId="sess-123")
    killed = []
    t = {"now": 0.0}
    with pytest.raises(tunnel.TunnelError, match="45"):
        with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=1,
                                spawn=make_spawn(), probe=lambda p: False, kill_group=lambda pid, sig=None: killed.append(pid),
                                log_dir=tmp_path, clock=lambda: t["now"],
                                sleep=lambda s: t.__setitem__("now", t["now"] + 10)):
            pass
    assert killed == [4242]


def test_spawn_missing_aws_cli(tmp_path, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(tunnel.subprocess, "Popen", boom)
    with pytest.raises(tunnel.TunnelError, match="aws"):
        tunnel._spawn(["aws"], tmp_path / "l.log")


def test_real_spawn_uses_new_session(tmp_path, monkeypatch):
    seen = {}

    class P:
        pid = 1

    def fake_popen(argv, **kw):
        seen.update(kw)
        return P()
    monkeypatch.setattr(tunnel.subprocess, "Popen", fake_popen)
    tunnel._spawn(["aws"], tmp_path / "l.log")
    assert seen["start_new_session"] is True


def test_kill_group_ignores_missing(monkeypatch):
    monkeypatch.setattr(tunnel.os, "killpg", lambda pid, sig: (_ for _ in ()).throw(ProcessLookupError()))
    tunnel._kill_group(1)  # no lanza
    got = []
    monkeypatch.setattr(tunnel.os, "killpg", lambda pid, sig: got.append((pid, sig)))
    tunnel._kill_group(7)
    assert got == [(7, signal.SIGTERM)]


def test_free_port_and_probe():
    p = tunnel.free_port()
    assert 1024 < p < 65536
    assert tunnel._port_open(p) is False


def test_pinned_connection_dials_loopback_but_keeps_sni(monkeypatch):
    seen = {}

    class Ctx:
        def wrap_socket(self, sock, server_hostname):
            seen["sni"] = server_hostname
            return "wrapped"

    monkeypatch.setattr(tunnel.socket, "create_connection",
                        lambda addr, timeout: seen.setdefault("addr", addr) and "raw")
    monkeypatch.setattr(tunnel.ssl, "create_default_context", lambda: Ctx())
    c = tunnel.PinnedHTTPSConnection("real.host", 443, ("127.0.0.1", 5555), 5)
    c.connect()
    assert seen == {"addr": ("127.0.0.1", 5555), "sni": "real.host"} and c.sock == "wrapped"
    assert c.host == "real.host"


def test_conn_factory():
    t = tunnel.Tunnel(local_port=5, remote_host="h", session_id=None, _proc=None, _ssm=None,
                      _kill=lambda p: None)
    c = t.connection_factory("h", 443, 7)
    assert c._connect_addr == ("127.0.0.1", 5)


def test_close_kills_group_even_if_wrapper_already_exited(stubbed, tmp_path):
    ssm = stubbed("ssm")
    ssm.ok("terminate_session", {}, SessionId="sess-123")
    sent = []
    proc = FakeProc(exit_code=0)  # el wrapper `aws` ya salió; el plugin hijo puede seguir vivo
    with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=1,
                            spawn=make_spawn(proc=proc), probe=lambda p: True,
                            kill_group=lambda pid, sig: sent.append((pid, sig)), log_dir=tmp_path):
        pass
    assert sent == [(4242, signal.SIGTERM)]


def test_close_escalates_to_sigkill(stubbed, tmp_path):
    ssm = stubbed("ssm")
    ssm.ok("terminate_session", {}, SessionId="sess-123")
    sent = []
    with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=1,
                            spawn=make_spawn(proc=FakeProc(hang=True)), probe=lambda p: True,
                            kill_group=lambda pid, sig: sent.append(sig), log_dir=tmp_path):
        pass
    assert sent == [signal.SIGTERM, signal.SIGKILL]


def test_session_id_read_lazily_at_close(stubbed, tmp_path):
    ssm = stubbed("ssm")
    ssm.ok("terminate_session", {}, SessionId="late-1")
    spawn = make_spawn(log_text="")  # al abrir todavía no hay SessionId en el log
    with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=7,
                            spawn=spawn, probe=lambda p: True, kill_group=lambda pid, sig=None: None,
                            log_dir=tmp_path):
        (tmp_path / "ssm-tunnel-7.log").write_text("Starting session with SessionId: late-1\n")


def test_temp_log_dir_is_removed(stubbed):
    ssm = stubbed("ssm")
    ssm.ok("terminate_session", {}, SessionId="sess-123")
    seen = {}

    def spawn(argv, log_path):
        seen["dir"] = log_path.parent
        log_path.write_text("SessionId: sess-123")
        return FakeProc()
    with tunnel.open_tunnel(profile="P", bastion="i", host="h", region="r", ssm=ssm.client, local_port=1,
                            spawn=spawn, probe=lambda p: True, kill_group=lambda pid, sig=None: None):
        assert seen["dir"].exists()
    assert not seen["dir"].exists()


def test_child_env_excludes_client_secret(tmp_path, monkeypatch):
    seen = {}

    class P:
        pid = 1
    monkeypatch.setattr(tunnel.subprocess, "Popen", lambda argv, **kw: seen.update(kw) or P())
    monkeypatch.setenv("IAE_CLIENT_SECRET", "topsecret")
    monkeypatch.setenv("KEEP_ME", "1")
    tunnel._spawn(["aws"], tmp_path / "l.log")
    assert "IAE_CLIENT_SECRET" not in seen["env"] and seen["env"]["KEEP_ME"] == "1"
