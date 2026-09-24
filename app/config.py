from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    inference_mode: Literal["local", "groq"] = "local"
    local_hardware_profile: Literal["mac_silicon", "rtx_3050a_4gb"] = "mac_silicon"
    groq_api_key: str = ""
    joy_modules: Literal["stub", "real"] = "stub"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    data_dir: Path = Path("./data")
    ollama_base_url: str = "http://localhost:11434"
    qdrant_url: str = "http://localhost:6333"
    max_upload_mb: int = 50
    max_pid_image_mb: int = 25
    max_message_chars: int = 20_000
    max_active_tasks: int = 2
    per_tool_timeout_s: int = 30
    model_generation_timeout_s: int = 60
    hard_task_timeout_s: int = 300
    approval_timeout_s: int = 86_400
    pid_timeout_s: int = 120
    sandbox_image: str = "indigent-sandbox:1"
    sandbox_mem_mb: int = 256
    sandbox_cpus: int = 1
    sandbox_pids: int = 64
    sandbox_output_limit_kb: int = 64
    workspace_ttl_hours: int = 24
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
