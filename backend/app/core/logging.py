"""Structured JSON logging with a redaction filter for secrets."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime

_SECRET_PATTERNS = [
    re.compile(r"(api[-_]?subscription[-_]?key|x-api-key|authorization|password|secret)"
               r"(['\"]?\s*[:=]\s*['\"]?)([^\s'\",}]+)", re.IGNORECASE),
    re.compile(r"sk-ant-[A-Za-z0-9_\-]+"),
    re.compile(r"eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+"),
]


def redact(message: str) -> str:
    message = _SECRET_PATTERNS[0].sub(lambda m: f"{m.group(1)}{m.group(2)}[redacted]", message)
    for pattern in _SECRET_PATTERNS[1:]:
        message = pattern.sub("[redacted]", message)
    return message


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # httpx logs full request URLs at INFO; keep them quiet.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpx2").setLevel(logging.WARNING)
    logging.getLogger("pypdf").setLevel(logging.ERROR)
