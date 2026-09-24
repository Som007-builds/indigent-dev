from app.config import Settings
from app.core.repo import Repository


class SovereigntyImpl:
    def __init__(self, repo: Repository, settings: Settings) -> None:
        self.repo, self.settings = repo, settings

    async def record_external_call(self, provider: str, bytes_out: int, bytes_in: int) -> None:
        """Record provider traffic; provider identity never determines inference mode."""
        await self.repo.increment_counter("external_api_calls")
        await self.repo.increment_counter("external_bytes_out", max(0, bytes_out))
        await self.repo.increment_counter("external_bytes_in", max(0, bytes_in))

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
            }
        return {
            "inference_mode": "groq", "status": "EXTERNAL INFERENCE ACTIVE", "provider": "Groq",
            "network_policy": "groq_endpoint_only", "internet_access": "ALLOWED (Groq endpoint only)", "sandbox_network": "disabled",
            "external_api_calls": counters["external_api_calls"], "external_connections": counters["external_connections"],
            "external_bytes_out": counters["external_bytes_out"], "external_bytes_in": counters["external_bytes_in"],
            "denied_connection_attempts": counters["denied_connections"], "since": counters["since"],
        }
