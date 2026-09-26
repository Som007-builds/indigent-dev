from app.config import Settings
from app.contracts.interfaces import AuditLogger
from app.core.repo import Repository


class SovereigntyImpl:
    def __init__(self, repo: Repository, settings: Settings, audit: AuditLogger | None = None) -> None:
        self.repo, self.settings = repo, settings
        self.audit = audit
        self._selections: dict[str, int] = {}
        self._selection_modes: dict[str, str] = {}

    async def record_external_call(self, provider: str, bytes_out: int, bytes_in: int) -> None:
        """Record provider traffic; provider identity never determines inference mode."""
        await self.repo.increment_counter("external_api_calls")
        await self.repo.increment_counter("external_bytes_out", max(0, bytes_out))
        await self.repo.increment_counter("external_bytes_in", max(0, bytes_in))

    async def record_model_selection(
        self, inference_mode: str, provider: str, model_id: str, *, task_id: str | None = None
    ) -> None:
        """Record which model served a task, without counting it as external traffic.

        Model selection is provenance, not egress, so it must not move the external
        counters. A model whose mode disagrees with the configured inference mode is a
        sovereignty violation and is audited explicitly, because the router is not
        supposed to be able to produce one.
        """
        mode = str(inference_mode)
        key = f"{mode}:{provider}:{model_id}"
        self._selections[key] = self._selections.get(key, 0) + 1
        self._selection_modes[key] = mode
        expected_provider = "ollama" if mode == "local" else "groq"
        if provider != expected_provider and self.audit is not None:
            await self.audit.emit(
                "PROVIDER_CALL",
                "sovereignty",
                "record_model_selection",
                "denied",
                task_id=task_id,
                details={
                    "reason": "MODEL_MODE_MISMATCH",
                    "inference_mode": mode,
                    "provider": provider,
                    "model_id": model_id,
                },
            )

    def model_selections(self) -> dict[str, int]:
        return dict(self._selections)

    async def snapshot(self) -> dict:
        counters = await self.repo.get_counters()
        mode = self.settings.inference_mode
        external = any(int(counters[name]) > 0 for name in ("external_api_calls", "external_connections", "external_bytes_out", "external_bytes_in"))
        if mode == "local":
            status = "AIR-GAP VIOLATED" if external else "AIR-GAPPED"
            return {
                "inference_mode": "local", "status": status, "provider": "ollama",
                "network_policy": "deny_all", "internet_access": "BLOCKED", "sandbox_network": "disabled",
                "external_api_calls": counters["external_api_calls"], "external_connections": counters["external_connections"],
                "external_bytes_out": counters["external_bytes_out"], "external_bytes_in": counters["external_bytes_in"],
                "denied_connection_attempts": counters["denied_connections"], "since": counters["since"],
                "models_selected": self.model_selections(),
            }
        return {
            "inference_mode": "groq", "status": "EXTERNAL INFERENCE ACTIVE", "provider": "Groq",
            "network_policy": "groq_endpoint_only", "internet_access": "ALLOWED (Groq endpoint only)", "sandbox_network": "disabled",
            "external_api_calls": counters["external_api_calls"], "external_connections": counters["external_connections"],
            "external_bytes_out": counters["external_bytes_out"], "external_bytes_in": counters["external_bytes_in"],
            "denied_connection_attempts": counters["denied_connections"], "since": counters["since"],
            "models_selected": self.model_selections(),
        }
