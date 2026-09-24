"""Process-level egress guard; OS firewall/container policy remain required layers."""
import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

from app.config import Settings
from app.errors import EgressDeniedError

_original_connect = socket.socket.connect
_original_connect_ex = socket.socket.connect_ex
_original_getaddrinfo = socket.getaddrinfo
_native_connect = _original_connect
_native_connect_ex = _original_connect_ex
_native_getaddrinfo = _original_getaddrinfo
_settings: Settings | None = None
_repo: Any = None
_audit: Any = None
_groq_ips: set[str] = set()


def install(settings: Settings, repo: Any, audit: Any) -> None:
    """Install once per process. The wrapped resolver never contacts disallowed hosts."""
    global _settings, _repo, _audit, _groq_ips
    _settings, _repo, _audit = settings, repo, audit
    _groq_ips = _resolve_groq() if settings.inference_mode == "groq" else set()
    socket.socket.connect = _connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _getaddrinfo  # type: ignore[assignment]


def uninstall() -> None:
    socket.socket.connect = _native_connect  # type: ignore[method-assign]
    socket.socket.connect_ex = _native_connect_ex  # type: ignore[method-assign]
    socket.getaddrinfo = _native_getaddrinfo  # type: ignore[assignment]


reset_for_testing = uninstall


def _resolve_groq() -> set[str]:
    try:
        return {item[4][0] for item in _original_getaddrinfo("api.groq.com", 443, type=socket.SOCK_STREAM)}
    except OSError:
        return set()


def _allowed_hosts() -> set[str]:
    assert _settings is not None
    return {urlparse(url).hostname or "" for url in (_settings.ollama_base_url, _settings.qdrant_url)}


def _is_local_or_private(host: str) -> bool:
    try:
        address = ipaddress.ip_address(host)
        return address.is_loopback or address.is_private
    except ValueError:
        return host.lower() == "localhost"


def _allowed(address: Any) -> tuple[bool, bool]:
    """Return (permitted, counts_as_external); unix sockets remain out of scope."""
    if not isinstance(address, tuple) or not address:
        return True, False
    host = str(address[0])
    if _is_local_or_private(host):
        return True, False
    if _settings and _settings.inference_mode == "groq" and host in _groq_ips:
        return True, True
    return False, False


def _connect(sock: socket.socket, address: Any) -> None:
    allowed, external = _allowed(address)
    if not allowed:
        _denied(str(address[0]))
    if external:
        _schedule(_repo.increment_counter("external_connections"))
    _original_connect(sock, address)


def _connect_ex(sock: socket.socket, address: Any) -> int:
    allowed, external = _allowed(address)
    if not allowed:
        _denied(str(address[0]))
    if external:
        _schedule(_repo.increment_counter("external_connections"))
    return _original_connect_ex(sock, address)


def _getaddrinfo(host: str | None, *args: Any, **kwargs: Any) -> list[Any]:
    if host is None or _is_local_or_private(host):
        return _original_getaddrinfo(host, *args, **kwargs)
    if host in _allowed_hosts():
        results = _original_getaddrinfo(host, *args, **kwargs)
        if all(_is_local_or_private(str(item[4][0])) for item in results):
            return results
        _denied(host)
    if _settings and _settings.inference_mode == "groq" and host == "api.groq.com":
        return _original_getaddrinfo(host, *args, **kwargs)
    _denied(host)
    raise AssertionError("unreachable")


def _denied(host: str) -> None:
    if _repo is not None:
        _schedule(_repo.increment_counter("denied_connections"))
    if _audit is not None:
        _schedule(_audit.emit("EGRESS_DENIED", "egress_guard", "connect", "denied", None, {"host": host}))
    raise EgressDeniedError()


def _schedule(coro: Any) -> None:
    try:
        asyncio.get_running_loop().create_task(coro)
    except RuntimeError:
        coro.close()
