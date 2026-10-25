import json
import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Any


class JsonFormatter(logging.Formatter):
    """Render ingestion logs as one JSON object per line."""

    _reserved = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

    def format(self, record: logging.LogRecord) -> str:
        event: dict[str, Any] = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        event.update(
            {
                key: value.isoformat() if isinstance(value, (date, datetime)) else str(value)
                if isinstance(value, Decimal)
                else value
                for key, value in record.__dict__.items()
                if key not in self._reserved and not key.startswith("_")
            }
        )
        return json.dumps(event, default=str, sort_keys=True)


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger
