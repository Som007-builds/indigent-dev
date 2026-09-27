from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from app.providers.types import ModelInfo


class ModelInventoryRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1)
    provider: Literal["ollama", "groq"]
    mode: Literal["local", "groq"]
    task_capabilities: frozenset[Literal["inspection", "coding", "pid_analysis"]]
    hardware_profiles: frozenset[Literal["mac_silicon", "rtx_3050a_4gb"]] = frozenset()
    memory_estimate_mb: int
    enabled: bool = True

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("model_id must not be blank")
        return value

    @field_validator("memory_estimate_mb")
    @classmethod
    def validate_memory(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("memory_estimate_mb must be positive")
        return value

    @model_validator(mode="after")
    def validate_mode_provider_profiles(self) -> "ModelInventoryRecord":
        if self.mode == "local":
            if self.provider != "ollama":
                raise ValueError("local models must use the ollama provider")
            if not self.hardware_profiles:
                raise ValueError("local models require at least one hardware profile")
        elif self.provider != "groq":
            raise ValueError("groq mode models must use the groq provider")
        elif self.hardware_profiles:
            raise ValueError("groq models must not declare local hardware profiles")
        return self

    def to_model_info(self) -> ModelInfo:
        from app.providers.types import ModelInfo

        return ModelInfo(
            model_id=self.model_id,
            model_name=self.model_id,
            provider=self.provider,
            mode=self.mode,
            task_types=self.task_capabilities,
            hardware_profiles=self.hardware_profiles,
            memory_estimate_mb=self.memory_estimate_mb,
            available=self.enabled,
        )


class Settings(BaseSettings):
    # INDIGENT_ENV_FILE lets an operator (and the hermetic test suite) point at a
    # different settings file. Tests must not inherit a developer's local .env.
    model_config = SettingsConfigDict(
        env_file=os.environ.get("INDIGENT_ENV_FILE", ".env"), extra="ignore"
    )

    inference_mode: Literal["local", "groq"] = "local"
    local_hardware_profile: Literal["mac_silicon", "rtx_3050a_4gb"] = "mac_silicon"
    groq_api_key: str = ""
    joy_modules: Literal["stub", "real"] = "stub"
    model_inventory_json: str | None = None
    # Optional explicit hardware budgets. Blank means "measure this machine for real".
    # Only set these when the allocation is genuinely known (for example a headless
    # runner with a fixed limit); they are never a fallback for a failed measurement.
    hardware_ram_budget_mb: int | None = Field(default=None, ge=1)
    hardware_vram_budget_mb: int | None = Field(default=None, ge=1)
    resource_max_concurrency: int = Field(default=1, ge=1)
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173"
    data_dir: Path = Path("./data")
    ollama_base_url: str = "http://localhost:11434"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "indigent_evidence"
    embedding_backend: Literal["ollama"] | None = None
    embedding_model: str | None = None
    embedding_vector_size: int | None = Field(default=None, ge=1)

    @field_validator("embedding_vector_size", mode="before")
    @classmethod
    def blank_vector_size_is_unprovisioned(cls, value: Any) -> Any:
        """Treat the shipped blank placeholder as "not provisioned yet".

        The declared .env.example ships this value blank in stub mode, and real mode
        rejects it in validate_rag_configuration() with an actionable message. Without
        this, a blank value aborts Settings construction with an opaque pydantic
        int_parsing error, so an operator cannot start the app to learn the real reason.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value
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

    def validate_rag_configuration(self) -> None:
        if not self.qdrant_collection.strip():
            raise ValueError("QDRANT_COLLECTION must not be empty")
        from urllib.parse import urlparse

        parsed = urlparse(self.qdrant_url)
        if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in {
            "localhost", "127.0.0.1", "::1"
        }:
            raise ValueError("QDRANT_URL must target a loopback host")
        if not self.embedding_backend or not self.embedding_model:
            raise ValueError("EMBEDDING_BACKEND and EMBEDDING_MODEL are required for production RAG")
        if self.embedding_vector_size is None or self.embedding_vector_size < 1:
            raise ValueError("EMBEDDING_VECTOR_SIZE must be positive for production RAG")

    def model_inventory(self) -> list[ModelInventoryRecord]:
        if self.model_inventory_json is None or not self.model_inventory_json.strip():
            raise ValueError("MODEL_INVENTORY_JSON is required for model routing")
        try:
            payload: Any = json.loads(self.model_inventory_json)
        except json.JSONDecodeError as error:
            raise ValueError("MODEL_INVENTORY_JSON must contain valid JSON") from error
        if not isinstance(payload, list) or not payload:
            raise ValueError("MODEL_INVENTORY_JSON must be a non-empty JSON array")
        try:
            records = [ModelInventoryRecord.model_validate(item) for item in payload]
        except (TypeError, ValueError) as error:
            raise ValueError("MODEL_INVENTORY_JSON contains an invalid model record") from error
        model_ids = [record.model_id for record in records]
        if len(set(model_ids)) != len(model_ids):
            raise ValueError("MODEL_INVENTORY_JSON contains duplicate model_id values")
        return records

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
