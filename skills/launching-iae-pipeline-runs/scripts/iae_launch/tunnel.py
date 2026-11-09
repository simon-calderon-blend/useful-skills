"""Port-forward SSM al API privado + cliente HTTPS con SNI fijado.

Port de pipeline_runner/tunnel.py:44-56,146-203 y api_client.py:131-176.
El API Gateway es privado (solo el VPCE lo alcanza): se reenvía un puerto local
por el bastión y se marca TLS con el hostname real (SNI + Host) para que el
certificado valide. Dos trampas de ciclo de vida, ambas cubiertas aquí:
* matar solo el wrapper ``aws`` deja vivo ``session-manager-plugin`` con el puerto:
  hay que matar el grupo de procesos;
* matar el proceso local deja la sesión ``Active`` en SSM: se termina explícitamente
  (el runner lo olvidaba).
"""

from __future__ import annotations

import http.client
import json
import logging
import os
import re
import shutil
import signal
import socket
import ssl
import subprocess
import tempfile
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterator

log = logging.getLogger("iae_launch.tunnel")
DOCUMENT_NAME = "AWS-StartPortForwardingSessionToRemoteHost"
READY_TIMEOUT = 45.0
KILL_GRACE = 10.0
SECRET_VAR = "IAE_CLIENT_SECRET"  # noqa: S105 - nombre de variable
POLL = 0.2
_SESSION_RE = re.compile(r"SessionId:\s*(\S+)")


class TunnelError(RuntimeError):
    pass


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _kill_group(pid: int, sig: int = signal.SIGTERM) -> None:
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError):
        pass


def _spawn(argv: list[str], log_path: Path) -> Any:
    # Archivo en vez de PIPE: un pipe lleno bloquearía al plugin si nadie lo lee.
    try:
        handle = log_path.open("wb")
    except OSError as exc:
        raise TunnelError(f"no se puede abrir el log del túnel {log_path}: {exc}") from None
    try:
        # El hijo (aws + session-manager-plugin) NO necesita el secreto del cliente.
        env = {k: v for k, v in os.environ.items() if k != SECRET_VAR}
        return subprocess.Popen(argv, stdout=handle, stderr=subprocess.STDOUT, env=env,
                                stdin=subprocess.DEVNULL, start_new_session=True)
    except FileNotFoundError:
        handle.close()
        raise TunnelError("el CLI `aws` no está en PATH (necesario para el túnel SSM)") from None


class PinnedHTTPSConnection(http.client.HTTPSConnection):
    """Conecta a ``connect_addr`` pero presenta ``host`` a TLS y a HTTP."""

    def __init__(self, host: str, port: int, connect_addr: tuple[str, int], timeout: float):
        super().__init__(host, port, timeout=timeout, context=ssl.create_default_context())
        self._connect_addr = connect_addr

    def connect(self) -> None:
        sock = socket.create_connection(self._connect_addr, self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


@dataclass
class Tunnel:
    local_port: int
    remote_host: str
    session_id: str | None
    _proc: Any
    _ssm: Any
    _kill: Callable[..., None]
    _closed: bool = False
    _log: Path | None = None
    _tmpdir: Path | None = None

    def connection_factory(self, host: str, port: int, timeout: float) -> PinnedHTTPSConnection:
        return PinnedHTTPSConnection(host, port, ("127.0.0.1", self.local_port), timeout)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._proc is not None:
            # Siempre el grupo: aunque el wrapper `aws` ya haya salido, el plugin hijo puede
            # seguir sujetando el puerto. Si no muere con SIGTERM, SIGKILL.
            self._kill(self._proc.pid, signal.SIGTERM)
            try:
                self._proc.wait(timeout=KILL_GRACE)
            except subprocess.TimeoutExpired:
                self._kill(self._proc.pid, signal.SIGKILL)
                try:
                    self._proc.wait(timeout=5)
                except Exception:  # noqa: BLE001
                    log.warning("el proceso del túnel no terminó tras SIGKILL")
            except Exception:  # noqa: BLE001 - el puerto debe liberarse igual
                log.warning("no se pudo esperar al proceso del túnel", exc_info=True)
        # El SessionId se lee AQUÍ (perezoso): puede haber aparecido en el log después de abrir.
        session_id = self.session_id or (_session_id(self._log) if self._log else None)
        if session_id and self._ssm is not None:
            try:
                self._ssm.terminate_session(SessionId=session_id)
            except Exception:  # noqa: BLE001 - nunca tapar la excepción en curso
                log.warning("no se pudo terminar la sesión SSM %s", session_id)
        if self._tmpdir is not None:
            shutil.rmtree(self._tmpdir, ignore_errors=True)


def _session_id(log: Path) -> str | None:
    try:
        m = _SESSION_RE.search(log.read_text(errors="replace"))
    except OSError:
        return None
    return m.group(1) if m else None


def _tail(log: Path, n: int = 400) -> str:
    try:
        text = log.read_text(errors="replace").strip()
    except OSError:
        return "(sin log)"
    return f"Log: {text[-n:]}" if text else "(log vacío)"


@contextmanager
def open_tunnel(*, profile: str, bastion: str, host: str, region: str, ssm: Any,
                port: int = 443, local_port: int | None = None, log_dir: Path | None = None,
                ready_timeout: float = READY_TIMEOUT,
                spawn: Callable[[list[str], Path], Any] = _spawn,
                probe: Callable[[int], bool] = _port_open,
                kill_group: Callable[..., None] = _kill_group,
                clock: Callable[[], float] = time.monotonic,
                sleep: Callable[[float], None] = time.sleep) -> Iterator[Tunnel]:
    local_port = local_port or free_port()
    tmpdir = None if log_dir else Path(tempfile.mkdtemp(prefix="iae-tunnel-"))
    log_path = (Path(log_dir) if log_dir else tmpdir) / f"ssm-tunnel-{local_port}.log"
    argv = ["aws", "ssm", "start-session", "--profile", profile, "--region", region,
            "--target", bastion, "--document-name", DOCUMENT_NAME,
            "--parameters", json.dumps({"host": [host], "portNumber": [str(port)],
                                        "localPortNumber": [str(local_port)]})]
    t: Tunnel | None = None
    try:
        proc = spawn(argv, log_path)
        t = Tunnel(local_port, host, None, proc, ssm, kill_group, _log=log_path, _tmpdir=tmpdir)
        deadline = clock() + ready_timeout
        while not probe(local_port):
            if proc.poll() is not None:
                detail = _tail(log_path)
                t.close()
                raise TunnelError(f"la sesión SSM a {host} vía {bastion} terminó antes de abrir "
                                  f"el túnel. {detail}")
            if clock() > deadline:
                detail = _tail(log_path)
                t.close()
                raise TunnelError(f"el puerto {local_port} no abrió en {ready_timeout:g}s "
                                  f"({host} vía {bastion}). {detail}")
            sleep(POLL)
        t.session_id = _session_id(log_path)
        yield t
    finally:
        if t is not None:
            t.close()
        elif tmpdir is not None:
            shutil.rmtree(tmpdir, ignore_errors=True)
