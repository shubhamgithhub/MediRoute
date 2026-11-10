"""Per-request tracing for Step 1.

Every stage of a request logs one event with the same ``request_id``:

* ``logs/step1_trace.jsonl``: one JSON object per line, full detail (machine-readable).
* ``logs/mediroute.log`` and the console: a one-line summary per event (human-readable).

Find everything about one request with, for example::

    Select-String -Path logs/step1_trace.jsonl -Pattern "<request_id>"

Patient text is logged after redaction (phone numbers, e-mails and ID numbers removed). Set
``MEDIROUTE_LOG_PATIENT_TEXT=0`` to log only a hash and length instead; do that before handling
any real patient data (DPDP).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from mediroute.utils.logging_config import get_logger
from mediroute.utils.paths import LOG_DIR

TRACE_FILE = LOG_DIR / "step1_trace.jsonl"
_SUMMARY_MAX = 220


def _trace_logger() -> logging.Logger:
    logger = logging.getLogger("mediroute.step1.trace")
    if not logger.handlers:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        handler = logging.FileHandler(TRACE_FILE, encoding="utf-8")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False  # the full JSON goes only to the trace file
    return logger


def log_patient_text() -> bool:
    return os.getenv("MEDIROUTE_LOG_PATIENT_TEXT", "1").strip().lower() not in {"0", "false", "no"}


def text_for_log(text: str) -> dict[str, Any]:
    """Redacted text when allowed, otherwise only a hash and length."""
    text = text or ""
    if log_patient_text():
        return {"text": text, "length": len(text)}
    return {"sha256_12": hashlib.sha256(text.encode("utf-8")).hexdigest()[:12], "length": len(text)}


def _short(value: Any) -> str:
    rendered = json.dumps(value, ensure_ascii=False, default=str)
    return rendered if len(rendered) <= _SUMMARY_MAX else rendered[: _SUMMARY_MAX - 3] + "..."


class Step1Trace:
    """Collects and logs the events of one Step 1 request."""

    def __init__(self, request_id: str | None = None, parent_request_id: str | None = None) -> None:
        self.request_id = request_id or uuid.uuid4().hex[:12]
        self.parent_request_id = parent_request_id
        self.events: list[dict[str, Any]] = []
        self._start = time.perf_counter()
        self._trace = _trace_logger()
        self._summary = get_logger()

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)

    def log(self, stage: str, **data: Any) -> None:
        event = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "request_id": self.request_id,
            "parent_request_id": self.parent_request_id,
            "stage": stage,
            "t_ms": self.elapsed_ms(),
            **data,
        }
        self.events.append(event)
        self._trace.info(json.dumps(event, ensure_ascii=False, default=str))
        summary = {k: v for k, v in data.items() if k not in {"prompt", "raw_response", "hits"}}
        self._summary.info("[step1 %s] %s %s", self.request_id, stage, _short(summary))
