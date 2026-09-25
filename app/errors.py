from dataclasses import dataclass


@dataclass
class AppError(Exception):
    code: str
    http_status: int
    message: str


class ToolNotAllowedError(AppError):
    def __init__(self, message: str = "Tool is not allowed") -> None:
        super().__init__("TOOL_NOT_ALLOWED", 403, message)


class PathRejectedError(AppError):
    def __init__(self, message: str = "Path was rejected") -> None:
        super().__init__("PATH_REJECTED", 400, message)


class SandboxUnavailableError(AppError):
    def __init__(self, message: str = "Sandbox is unavailable") -> None:
        super().__init__("SANDBOX_UNAVAILABLE", 503, message)


class ArtifactCorruptError(AppError):
    def __init__(self, message: str = "Artifact is corrupt") -> None:
        super().__init__("ARTIFACT_CORRUPT", 500, message)


class EgressDeniedError(AppError):
    def __init__(self, message: str = "Network egress denied") -> None:
        super().__init__("EGRESS_DENIED", 403, message)


class ModelUnavailableError(AppError):
    def __init__(self, message: str = "No available model matches the request") -> None:
        super().__init__("MODEL_UNAVAILABLE", 503, message)
