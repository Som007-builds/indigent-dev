from app.config import Settings
from app.errors import ModelUnavailableError
from app.providers import InferenceProvider, ModelInfo

from .registry import ModelRegistry
from .resource_manager import ResourceManager


def _accepts_images(provider: InferenceProvider) -> bool:
    """Fail closed for image-only work when the adapter does not declare image support."""
    capability = getattr(provider, "supports_images", None)
    if capability is None:
        return False
    return bool(capability() if callable(capability) else capability)


class ModelRouter:
    def __init__(
        self,
        settings: Settings,
        registry: ModelRegistry,
        providers: dict[str, InferenceProvider],
        resources: ResourceManager | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.providers = providers
        self.resources = resources

    def resolve(
        self, task_type: str, requested_model_id: str | None = None, *, requires_images: bool = False
    ) -> tuple[ModelInfo, InferenceProvider]:
        mode = self.settings.inference_mode
        if requested_model_id is not None:
            model = self.registry.get(requested_model_id)
            candidates = [model] if model is not None else []
        else:
            candidates = self.registry.candidates(
                task_type, mode, self.settings.local_hardware_profile
            )
        # Sync Ollama residency so ResourceManager knows about models loaded outside its control
        if self.resources is not None:
            self.resources.sync_ollama_residency(self.settings.ollama_base_url)
        for model in candidates:
            if model is None or model.mode != mode or not model.available:
                continue
            if task_type not in model.task_types:
                continue
            if model.mode == "local" and self.settings.local_hardware_profile not in model.hardware_profiles:
                continue
            if self.resources is not None and not self.resources.can_select(model):
                continue
            provider = self.providers.get(model.provider)
            if provider is None or provider.is_local() != (mode == "local"):
                continue
            if requires_images:
                if "image" not in model.modalities:
                    continue
                if not _accepts_images(provider):
                    continue
            health = provider.health_check()
            if health.available:
                return model, provider
        raise ModelUnavailableError(
            f"No available {mode} model for task type {task_type!r} "
            f"and hardware profile {self.settings.local_hardware_profile!r}"
        )
