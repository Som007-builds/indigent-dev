import logging

from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.logging_setup import configure_logging
from app.main import create_app


def test_health_has_required_headers(tmp_path):
    client = TestClient(create_app(Settings(data_dir=tmp_path)))
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.headers["x-inference-mode"] == "local"
    assert response.headers["x-request-id"]


def test_invalid_inference_mode_refuses_startup():
    try:
        Settings(inference_mode="x")
    except ValidationError:
        return
    raise AssertionError("invalid inference mode was accepted")


def test_logs_redact_groq_secret(tmp_path):
    configure_logging(tmp_path, "INFO")
    logging.getLogger("test").info("credential gsk_test123")
    assert "gsk_test123" not in (tmp_path / "logs" / "app.log").read_text()
