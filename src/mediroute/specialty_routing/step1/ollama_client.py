"""Small Ollama client that returns everything the trace needs about each LLM call."""

from __future__ import annotations

import json
import os
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL = os.getenv("MEDIROUTE_LLM_MODEL", "llama3.2")
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_API_BASE_URL", "http://localhost:11434")
DEFAULT_TIMEOUT_S = float(os.getenv("MEDIROUTE_LLM_TIMEOUT_S", "90"))


@dataclass
class LLMCall:
    ok: bool
    parsed: dict[str, Any] = field(default_factory=dict)
    raw_response: str = ""
    error: str | None = None
    duration_ms: int = 0
    details: dict[str, Any] = field(default_factory=dict)  # model, options, token counts, ollama timings


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, base_url: str = DEFAULT_OLLAMA_URL,
                 timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def warm_up(self) -> None:
        self._post({"model": self.model, "prompt": "ok", "stream": False, "keep_alive": "30m",
                    "options": {"num_predict": 1}})

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        options = {"temperature": 0, "seed": 7}
        details: dict[str, Any] = {"purpose": purpose, "model": self.model, "endpoint": f"{self.base_url}/api/generate",
                                   "options": options, "prompt_chars": len(prompt), "timeout_s": self.timeout_s}
        start = time.perf_counter()
        try:
            body = self._post({"model": self.model, "prompt": prompt, "stream": False, "format": schema,
                               "keep_alive": "30m", "options": options})
        except Exception as exc:  # network error, timeout, Ollama down
            return LLMCall(False, error=f"{type(exc).__name__}: {exc}",
                           duration_ms=int((time.perf_counter() - start) * 1000), details=details)
        duration = int((time.perf_counter() - start) * 1000)
        raw = body.get("response") or ""
        details.update({
            "prompt_tokens": body.get("prompt_eval_count"),
            "output_tokens": body.get("eval_count"),
            "ollama_total_ms": int((body.get("total_duration") or 0) / 1e6),
            "ollama_load_ms": int((body.get("load_duration") or 0) / 1e6),
        })
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            return LLMCall(False, raw_response=raw, error=f"bad JSON: {exc}", duration_ms=duration, details=details)
        return LLMCall(True, parsed=parsed if isinstance(parsed, dict) else {}, raw_response=raw,
                       duration_ms=duration, details=details)
