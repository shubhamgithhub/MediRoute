"""LLM clients for Step 1. Each call returns everything the trace needs (LLMCall).

Step 1 must work without an LLM: teammates may not have Ollama installed. Choose the client with
MEDIROUTE_LLM_PROVIDER:

    ollama  (default) local Ollama at OLLAMA_API_BASE_URL. If it isn't running, or the model isn't
            pulled, Step 1 logs a warning and carries on without it (evidence from keywords, V3
            abstains, V1 + V2 must agree). It re-checks every 60 s, so starting Ollama later works.
    none    no LLM at all, same fallback, no connection attempts.

A hosted model (e.g. OpenAI with an API key) goes in make_llm_client(): any class with ``model``,
``status()``, ``warm_up()`` and ``generate_json(prompt, schema, purpose) -> LLMCall`` works.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any

DEFAULT_MODEL = os.getenv("MEDIROUTE_LLM_MODEL", "llama3.2")
# 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first, Ollama listens on IPv4
# only, and every call waited ~2 s for the fallback (measured 2026-11-10).
DEFAULT_OLLAMA_URL = os.getenv("OLLAMA_API_BASE_URL", "http://127.0.0.1:11434")
DEFAULT_TIMEOUT_S = float(os.getenv("MEDIROUTE_LLM_TIMEOUT_S", "90"))
CHECK_TIMEOUT_S = 3.0  # availability check: is Ollama up and is the model pulled?
RECHECK_AFTER_S = 60.0  # while unavailable, skip calls instantly and look again after this long


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
        self.provider = "ollama"
        self._available: bool | None = None  # None = not checked yet
        self._reason = ""
        self._checked_at = 0.0

    # ------------------------------------------------------------------ availability
    def status(self, force: bool = False) -> dict[str, Any]:
        """Is the LLM usable? Cached; re-checked after RECHECK_AFTER_S while it is down."""
        stale = self._available is not True and time.monotonic() - self._checked_at > RECHECK_AFTER_S
        if force or self._available is None or stale:
            self._available, self._reason = self._check()
            self._checked_at = time.monotonic()
        return {"provider": self.provider, "model": self.model, "available": bool(self._available),
                "reason": self._reason}

    def _check(self) -> tuple[bool, str]:
        try:
            with urllib.request.urlopen(f"{self.base_url}/api/tags", timeout=CHECK_TIMEOUT_S) as response:
                models = json.loads(response.read().decode("utf-8")).get("models", [])
        except Exception as exc:
            return False, (f"Ollama is not reachable at {self.base_url} ({type(exc).__name__}). "
                           "Install and start Ollama, or set MEDIROUTE_LLM_PROVIDER=none")
        names = {m.get("name", "") for m in models}
        if self.model not in names and f"{self.model}:latest" not in names:
            return False, f"Ollama is running but model '{self.model}' is not pulled: run 'ollama pull {self.model}'"
        return True, ""

    def _mark_down(self, exc: Exception) -> None:
        """A refused connection means Ollama went away: skip calls until the next re-check."""
        if isinstance(exc, (ConnectionError, urllib.error.URLError)) and not isinstance(exc, TimeoutError):
            self._available, self._checked_at = False, time.monotonic()
            self._reason = f"Ollama stopped answering ({type(exc).__name__}: {exc})"

    def _post(self, payload: dict) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def warm_up(self) -> None:
        state = self.status(force=True)
        if not state["available"]:
            raise RuntimeError(state["reason"])
        self._post({"model": self.model, "prompt": "ok", "stream": False, "keep_alive": "30m",
                    "options": {"num_predict": 1}})

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        options = {"temperature": 0, "seed": 7}
        details: dict[str, Any] = {"purpose": purpose, "model": self.model, "endpoint": f"{self.base_url}/api/generate",
                                   "options": options, "prompt_chars": len(prompt), "timeout_s": self.timeout_s}
        state = self.status()
        if not state["available"]:  # skip instantly instead of waiting for a refused connection
            details["skipped"] = True
            return LLMCall(False, error=f"LLM unavailable: {state['reason']}", details=details)
        start = time.perf_counter()
        try:
            body = self._post({"model": self.model, "prompt": prompt, "stream": False, "format": schema,
                               "keep_alive": "30m", "options": options})
        except Exception as exc:  # network error, timeout, Ollama down
            self._mark_down(exc)
            return LLMCall(False, error=f"{type(exc).__name__}: {exc}",
                           duration_ms=int((time.perf_counter() - start) * 1000), details=details)
        duration = int((time.perf_counter() - start) * 1000)
        raw = body.get("response") or ""
        details.update({
            "prompt_tokens": body.get("prompt_eval_count"),
            "output_tokens": body.get("eval_count"),
            "ollama_total_ms": int((body.get("total_duration") or 0) / 1e6),
            "ollama_load_ms": int((body.get("load_duration") or 0) / 1e6),
            # where Ollama's time goes: reading the prompt vs writing the answer
            "ollama_prompt_eval_ms": int((body.get("prompt_eval_duration") or 0) / 1e6),
            "ollama_generate_ms": int((body.get("eval_duration") or 0) / 1e6),
        })
        try:
            parsed = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            return LLMCall(False, raw_response=raw, error=f"bad JSON: {exc}", duration_ms=duration, details=details)
        return LLMCall(True, parsed=parsed if isinstance(parsed, dict) else {}, raw_response=raw,
                       duration_ms=duration, details=details)


class DisabledLLMClient:
    """MEDIROUTE_LLM_PROVIDER=none: no LLM; Step 1 runs on keyword evidence and the two search voters."""

    provider = "none"
    model = "none"
    REASON = "LLM turned off (MEDIROUTE_LLM_PROVIDER=none)"

    def status(self, force: bool = False) -> dict[str, Any]:
        return {"provider": self.provider, "model": self.model, "available": False, "reason": self.REASON}

    def warm_up(self) -> None:
        raise RuntimeError(self.REASON)

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        return LLMCall(False, error=f"LLM unavailable: {self.REASON}",
                       details={"purpose": purpose, "model": self.model, "skipped": True})


def make_llm_client():
    """The Step 1 LLM client chosen by MEDIROUTE_LLM_PROVIDER (add hosted providers here)."""
    provider = os.getenv("MEDIROUTE_LLM_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        return OllamaClient()
    if provider in {"none", "off", "disabled"}:
        return DisabledLLMClient()
    raise ValueError(f"Unknown MEDIROUTE_LLM_PROVIDER '{provider}': use 'ollama' or 'none'")
