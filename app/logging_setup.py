import contextvars
import json
import logging
import re
import sys
from pathlib import Path

request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
task_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("task_id", default=None)
_SECRET_KEY = re.compile(r"(?i)(key|token|secret|authorization|password)")
_GROQ_SECRET = re.compile(r"gsk_[A-Za-z0-9]+")


def redact(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(k): "[REDACTED]" if _SECRET_KEY.search(str(k)) else redact(v)
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _GROQ_SECRET.sub("[REDACTED]", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "message": redact(record.getMessage())}
        if request_id.get():
            payload["request_id"] = request_id.get()
        if task_id.get():
            payload["task_id"] = task_id.get()
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)



def configure_logging(data_dir: Path, level: str) -> None:
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    formatter = JsonFormatter()
    logger = logging.getLogger()
    logger.handlers.clear()
    logger.setLevel(level.upper())
    for handler in (logging.StreamHandler(sys.stdout), logging.FileHandler(log_dir / "app.log")):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
