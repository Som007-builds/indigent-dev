import asyncio
import socket

import pytest
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.core.audit import AuditLoggerImpl
from app.core.db import Database
from app.core.repo import Repository
from app.errors import EgressDeniedError
from app.main import create_app
from app.net import egress_guard
from app.net.sovereignty import SovereigntyImpl


async def _components(tmp_path, mode="local"):
    settings = Settings(data_dir=tmp_path, inference_mode=mode)
    repo = Repository(Database(tmp_path / "db.sqlite"))
    await repo.db.initialize()
    return settings, repo, AuditLoggerImpl(repo, settings)


@pytest.mark.asyncio
async def test_local_sovereignty_is_air_gapped_and_external_calls_count(tmp_path):
    settings, repo, _ = await _components(tmp_path)
    sovereignty = SovereigntyImpl(repo, settings)
    snapshot = await sovereignty.snapshot()
    assert snapshot["status"] == "AIR-GAPPED"
    assert all(snapshot[name] == 0 for name in snapshot if name.startswith("external_"))
    for _ in range(12):
        await sovereignty.record_external_call("ignored", 2, 3)
    snapshot = await sovereignty.snapshot()
    assert snapshot["external_api_calls"] == 12
    assert snapshot["external_bytes_out"] == 24


@pytest.mark.asyncio
@pytest.mark.parametrize("counter", ["external_api_calls", "external_connections", "external_bytes_out"])
async def test_groq_never_reports_air_gapped(tmp_path, counter):
    settings, repo, _ = await _components(tmp_path, "groq")
    await repo.increment_counter(counter)
    snapshot = await SovereigntyImpl(repo, settings).snapshot()
    assert snapshot["status"] == "EXTERNAL INFERENCE ACTIVE"
    assert "AIR-GAPPED" not in snapshot["status"]


@pytest.mark.asyncio
async def test_local_external_counter_is_an_air_gap_violation(tmp_path):
    settings, repo, _ = await _components(tmp_path)
    await repo.increment_counter("external_connections")
    assert (await SovereigntyImpl(repo, settings).snapshot())["status"] == "AIR-GAP VIOLATED"


@pytest.mark.asyncio
async def test_egress_guard_denies_public_ip_without_network(monkeypatch, tmp_path):
    settings, repo, audit = await _components(tmp_path)
    monkeypatch.setattr(egress_guard, "_original_connect", lambda *_: None)
    egress_guard.install(settings, repo, audit)
    sock = socket.socket()
    try:
        with pytest.raises(EgressDeniedError):
            sock.connect(("93.184.216.34", 80))
        await asyncio.sleep(0.1)
        counters = await repo.get_counters()
        assert counters["denied_connections"] == 1
        assert counters["external_connections"] == 0
        assert (await repo.list_audit())[0]["category"] == "EGRESS_DENIED"
        sock.connect(("127.0.0.1", 8000))
    finally:
        sock.close()
        egress_guard.reset_for_testing()


@pytest.mark.asyncio
async def test_egress_guard_resolves_loopback_passed_as_bytes(monkeypatch, tmp_path):
    """asyncio hands getaddrinfo a bytes host; loopback must still resolve."""
    settings, repo, audit = await _components(tmp_path)
    monkeypatch.setattr(
        egress_guard, "_original_getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("127.0.0.1", 6333))]
    )
    permitted: list = []
    monkeypatch.setattr(egress_guard, "_original_connect", lambda _, address: permitted.append(address))
    egress_guard.install(settings, repo, audit)
    try:
        assert egress_guard.socket.getaddrinfo(b"localhost", 6333, type=socket.SOCK_STREAM)
        assert egress_guard.socket.getaddrinfo("localhost", 6333, type=socket.SOCK_STREAM)
        sock = socket.socket()
        try:
            sock.connect((b"127.0.0.1", 8000))
        finally:
            sock.close()
        assert permitted == [(b"127.0.0.1", 8000)]
        with pytest.raises(EgressDeniedError):
            egress_guard.socket.getaddrinfo(b"api.groq.com", 443, type=socket.SOCK_STREAM)
    finally:
        egress_guard.reset_for_testing()


@pytest.mark.asyncio
async def test_models_failure_returns_clean_503(tmp_path):
    class BrokenModels:
        def status(self):
            raise RuntimeError("secret traceback")

    app = create_app(Settings(data_dir=tmp_path), BrokenModels())
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/api/models")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "MODELS_UNAVAILABLE"
    assert "traceback" not in response.text
