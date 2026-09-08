"""Standard-library JSON logging configuration for the Worker service."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Final

_LOG_RECORD_FIELDS: Final[frozenset[str]] = frozenset(logging.makeLogRecord({}).__dict__)


class JsonFormatter(logging.Formatter):
    """Serialize log records and their contextual fields as JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        payload.update(
            {
                name: value
                for name, value in record.__dict__.items()
                if name not in _LOG_RECORD_FIELDS
            }
        )
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, separators=(",", ":"), sort_keys=True)


def configure_json_logging(level: int | str) -> None:
    """Configure root logging to emit JSON records to standard error."""

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=level, handlers=[handler], force=True)
