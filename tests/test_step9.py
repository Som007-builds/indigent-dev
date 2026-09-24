from pathlib import Path

from app.config import Settings


def test_shipped_environment_and_settings_default_to_local_mode() -> None:
    env_example = Path(".env.example").read_text(encoding="utf-8")
    assert "INFERENCE_MODE=local" in env_example.splitlines()
    assert Settings(_env_file=None).inference_mode == "local"


def test_compose_is_qdrant_only_and_binds_rest_to_loopback() -> None:
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "qdrant/qdrant:v1.19.1" in compose
    assert '"127.0.0.1:6333:6333"' in compose
    assert "QDRANT__TELEMETRY_DISABLED" in compose
    assert "restart: unless-stopped" in compose
    assert "services:\n  qdrant:" in compose
    assert compose.count("image:") == 1
