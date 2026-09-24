import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path, PureWindowsPath

from app.config import Settings
from app.errors import PathRejectedError


def safe_join(root: Path, user_path: str | Path) -> Path:
    """Join an untrusted relative path without allowing it to escape *root*."""
    raw = str(user_path)
    if not raw or "\x00" in raw:
        raise PathRejectedError("Path is empty or contains a NUL byte")
    # Interpret both platform path dialects: Windows separators are dangerous on Unix too.
    if (
        Path(raw).is_absolute()
        or PureWindowsPath(raw).is_absolute()
        or PureWindowsPath(raw).drive
        or any(part == ".." for part in raw.replace("\\", "/").split("/"))
    ):
        raise PathRejectedError("Path must be a relative path inside its workspace")
    resolved_root = root.resolve()
    candidate = (resolved_root / raw.replace("\\", "/")).resolve()
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise PathRejectedError("Path escapes its workspace") from exc
    # resolve() follows existing symlinks; explicitly inspect existing components for clarity.
    current = resolved_root
    for part in candidate.relative_to(resolved_root).parts:
        current /= part
        if current.exists() and current.is_symlink() and not current.resolve().is_relative_to(resolved_root):
            raise PathRejectedError("Path contains a symlink escaping its workspace")
    return candidate


def create_workspace(workspace_root: Path, task_id: str) -> Path:
    workspace = safe_join(workspace_root, task_id)
    for name in ("inputs", "outputs", "code", "scratch"):
        safe_join(workspace, name).mkdir(parents=True, exist_ok=True)
    return workspace


def cleanup_expired(settings: Settings) -> int:
    root = settings.data_dir / "workspaces"
    if not root.exists():
        return 0
    cutoff = datetime.now(UTC) - timedelta(hours=settings.workspace_ttl_hours)
    removed = 0
    for workspace in root.iterdir():
        if workspace.is_dir() and datetime.fromtimestamp(workspace.stat().st_mtime, UTC) < cutoff:
            scratch = safe_join(workspace, "scratch")
            if scratch.exists():
                shutil.rmtree(scratch)
                removed += 1
    return removed
