from collections.abc import Iterable

from app.providers import ModelInfo


class ModelRegistry:
    def __init__(self, models: Iterable[ModelInfo] = ()) -> None:
        self._models = {model.model_id: model for model in models}

    def register(self, model: ModelInfo) -> None:
        self._models[model.model_id] = model

    def get(self, model_id: str) -> ModelInfo | None:
        return self._models.get(model_id)

    def models(self) -> list[ModelInfo]:
        return list(self._models.values())

    def candidates(
        self, task_type: str, mode: str, hardware_profile: str
    ) -> list[ModelInfo]:
        return [
            model
            for model in self._models.values()
            if model.mode == mode
            and task_type in model.task_types
            and (mode != "local" or hardware_profile in model.hardware_profiles)
        ]
