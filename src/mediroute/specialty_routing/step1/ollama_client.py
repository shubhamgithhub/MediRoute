"""LLM clients for Step 1. Each call returns everything the trace needs (LLMCall).

Step 1 must work without an LLM: teammates may not have Ollama installed. Choose the client with
MEDIROUTE_LLM_PROVIDER:

    ollama  (default) local Ollama at OLLAMA_API_BASE_URL. If it isn't running, or the model isn't
            pulled, Step 1 logs a warning and carries on without it (evidence from keywords, V3
            abstains, V1 + V2 must agree). It re-checks every 60 s, so starting Ollama later works.
    openrouter  hosted models via OpenRouter (free tier works). Needs OPENROUTER_API_KEY (each
            teammate uses their own key; free tier = 50 requests/day, 20/min). Model from
            MEDIROUTE_OPENROUTER_MODEL (default: a free model with JSON-schema support).
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


# ---------------------------------------------------------------------------- OpenRouter
OPENROUTER_URL = "https://openrouter.ai/api/v1"
# Free models tried in order; one that is rate-limited upstream or refuses is skipped for 60 s.
# Compared 2026-11-10 on the real V3 prompt, reasoning off: dots-3-note 2.3 s (1.2 s to first
# token), nemotron-3.5-super ~13-15 s (free queue); gemma-4 and xing4.0 were rate-limited upstream;
# flint and lfm refuse to run without reasoning; inkling-2-small returned 403. dots-3-note-preview
# expires 2026-12-31. Pin a single model for evaluation runs ("openrouter/free" changes per request).
DEFAULT_OPENROUTER_MODEL = "dots-studio/dots-3-note-preview:free,nvidia/nemotron-3.5-super-vl:free"
# Hidden reasoning was ~95% of the output tokens of the default model (e.g. 829 of 856) and most of
# the wait; routing doesn't need it. Set MEDIROUTE_OPENROUTER_REASONING=on to allow it.
REASONING_ON = os.getenv("MEDIROUTE_OPENROUTER_REASONING", "off").strip().lower() in {"on", "1", "true"}
MAX_RETRY_WAIT_S = 20.0  # per-minute 429: wait (Retry-After) and retry once; longer limits mark it down
CODE_FENCE = "`" * 3


class _ProviderError(Exception):
    """An HTTP error, or an error chunk inside the stream, with its code and message."""

    def __init__(self, code: int, text: str, retry_after: float = 0.0) -> None:
        super().__init__(f"HTTP {code}: {text}")
        self.code, self.text, self.retry_after = code, text, retry_after

    @property
    def account_level(self) -> bool:
        """Bad key, no credit, or the daily free limit: no other model will work either."""
        return self.code in (401, 402) or (self.code == 429 and "per-day" in self.text.lower())

    @property
    def model_level(self) -> bool:
        """This model is busy upstream, gone, or refuses our settings: try the next model."""
        return self.code in (403, 404, 429, 502, 503) or "reasoning is mandatory" in self.text.lower()


def _read_api_key(name: str) -> str:
    """From the environment, or on Windows from the user's saved variables (setx), so a terminal
    opened before setx still works."""
    value = os.getenv(name, "").strip()
    if value or os.name != "nt":
        return value
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
            return str(winreg.QueryValueEx(key, name)[0]).strip()
    except OSError:
        return ""


class OpenRouterClient:
    """OpenAI-compatible chat completions via OpenRouter, with the same LLMCall details as Ollama."""

    provider = "openrouter"
    needs_priming = False  # no local prompt cache to warm, and each call counts against the free limit
    parallel_calls = True  # hosted: the evidence and V3 calls can run at the same time

    def __init__(self, model: str | None = None, api_key: str | None = None, base_url: str = OPENROUTER_URL,
                 timeout_s: float = DEFAULT_TIMEOUT_S) -> None:
        spec = model or os.getenv("MEDIROUTE_OPENROUTER_MODEL", DEFAULT_OPENROUTER_MODEL)
        self.models = [m.strip() for m in spec.split(",") if m.strip()]
        self.model = self.models[0]
        self._model_down: dict[str, tuple[float, str]] = {}  # model -> (when, why)
        self.api_key = api_key if api_key is not None else _read_api_key("OPENROUTER_API_KEY")
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s
        self.key_info: dict[str, Any] = {}
        self._down_reason = "" if self.api_key else (
            "OPENROUTER_API_KEY is not set (create a key at openrouter.ai/settings/keys, then setx it)")
        self._down_at = 0.0 if self.api_key else float("inf")  # no key: never re-check

    def status(self, force: bool = False) -> dict[str, Any]:
        recheck = self._down_at != float("inf") and time.monotonic() - self._down_at > RECHECK_AFTER_S
        if self._down_reason and recheck:
            self._down_reason = ""  # try again; a rate limit or outage may have cleared
        return {"provider": self.provider, "model": self.model, "available": not self._down_reason,
                "reason": self._down_reason}

    def _request(self, path: str, payload: dict | None = None) -> dict:
        request = urllib.request.Request(
            f"{self.base_url}{path}", data=json.dumps(payload).encode("utf-8") if payload is not None else None,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "X-OpenRouter-Title": "MediRoute (capstone)"})
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            return json.loads(response.read().decode("utf-8"))

    def _stream_chat(self, payload: dict) -> dict:
        """Streams the completion so we can time the wait before the first token ourselves.

        Returns content, usage, model, provider, id, first_token_ms and reasoning_chars."""
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions", data=json.dumps({**payload, "stream": True}).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json",
                     "X-OpenRouter-Title": "MediRoute (capstone)"})
        start = time.perf_counter()
        out: dict[str, Any] = {"content": "", "usage": {}, "first_token_ms": None, "reasoning_chars": 0}
        with urllib.request.urlopen(request, timeout=self.timeout_s) as response:
            for line in response:
                line = line.decode("utf-8", "replace").strip()
                if not line.startswith("data:"):
                    continue  # blank lines and ": OPENROUTER PROCESSING" keep-alives
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                chunk = json.loads(data)
                if chunk.get("error"):
                    error = chunk["error"]
                    code = int(error.get("code") or 500) if isinstance(error, dict) else 500
                    message = error.get("message", str(error)) if isinstance(error, dict) else str(error)
                    raise _ProviderError(code, message[:300])
                for key in ("id", "model", "provider"):
                    out.setdefault(key, chunk.get(key))
                if chunk.get("usage"):
                    out["usage"] = chunk["usage"]
                for choice in chunk.get("choices") or []:
                    delta = choice.get("delta") or {}
                    piece, thought = delta.get("content") or "", delta.get("reasoning") or ""
                    if (piece or thought) and out["first_token_ms"] is None:
                        out["first_token_ms"] = int((time.perf_counter() - start) * 1000)
                    out["content"] += piece
                    out["reasoning_chars"] += len(thought)
        return out

    def _mark_down(self, reason: str, permanent: bool = False) -> None:
        self._down_reason = reason
        self._down_at = float("inf") if permanent else time.monotonic()

    def warm_up(self) -> None:
        """Checks the key and the free-tier limit without spending a request."""
        if not self.api_key:
            raise RuntimeError(self._down_reason)
        try:
            info = self._request("/key").get("data", {})
        except urllib.error.HTTPError as exc:
            self._mark_down(f"OpenRouter key rejected (HTTP {exc.code})", permanent=exc.code == 401)
            raise RuntimeError(self._down_reason) from exc
        self.key_info = {k: info.get(k) for k in ("limit", "usage", "is_free_tier", "limit_remaining")}

    def _models_to_try(self) -> list[str]:
        now = time.monotonic()
        ready = [m for m in self.models if now - self._model_down.get(m, (-1e9, ""))[0] > RECHECK_AFTER_S]
        return ready or self.models[:1]  # all recently failed: try the first one again

    def _call_model(self, model: str, payload: dict) -> dict:
        """One model, with one retry when a per-minute limit says to wait briefly."""
        for attempt in range(2):
            try:
                return self._stream_chat({**payload, "model": model})
            except urllib.error.HTTPError as exc:
                text = exc.read().decode("utf-8", "replace")[:300]
                wait = float(exc.headers.get("Retry-After") or 0) if exc.headers else 0.0
                error = _ProviderError(exc.code, text, wait)
            if error.code == 429 and attempt == 0 and 0 < error.retry_after <= MAX_RETRY_WAIT_S:
                time.sleep(error.retry_after)
                continue
            raise error
        raise error

    def generate_json(self, prompt: str, schema: dict, purpose: str) -> LLMCall:
        options = {"temperature": 0, "seed": 7}
        details: dict[str, Any] = {"purpose": purpose, "provider": self.provider, "model": self.model,
                                   "endpoint": f"{self.base_url}/chat/completions", "options": options,
                                   "prompt_chars": len(prompt), "timeout_s": self.timeout_s,
                                   "reasoning_enabled": REASONING_ON}
        state = self.status()
        if not state["available"]:
            details["skipped"] = True
            return LLMCall(False, error=f"LLM unavailable: {state['reason']}", details=details)
        payload = {"messages": [{"role": "user", "content": prompt}], **options,
                   "reasoning": {"enabled": REASONING_ON},
                   "response_format": {"type": "json_schema",
                                       "json_schema": {"name": purpose, "strict": False, "schema": schema}}}
        start = time.perf_counter()
        body: dict = {}
        tried: list[dict[str, str]] = []
        for model in self._models_to_try():
            try:
                body = self._call_model(model, payload)
                details["model"] = model
                break
            except _ProviderError as error:
                tried.append({"model": model, "error": str(error)[:200]})
                if error.account_level:
                    self._mark_down(f"OpenRouter {error}", permanent=error.code == 401)
                    break
                if error.model_level:
                    self._model_down[model] = (time.monotonic(), str(error)[:200])
                    continue  # next model
                break
            except Exception as exc:  # network error, timeout, bad stream
                tried.append({"model": model, "error": f"{type(exc).__name__}: {exc}"[:200]})
                break
        if tried:
            details["models_tried"] = tried  # failures before the answer (or all failures), for the trace
        if not body:
            return LLMCall(False, error=tried[-1]["error"] if tried else "no model answered",
                           duration_ms=int((time.perf_counter() - start) * 1000), details=details)
        duration = int((time.perf_counter() - start) * 1000)
        usage = body.get("usage") or {}
        first = body.get("first_token_ms")
        details.update({"model_used": body.get("model"), "upstream_provider": body.get("provider"),
                        "generation_id": body.get("id"), "prompt_tokens": usage.get("prompt_tokens"),
                        "output_tokens": usage.get("completion_tokens"), "cost": usage.get("cost"),
                        # where the time goes: waiting for the first token (queue) vs writing tokens
                        "first_token_ms": first,
                        "generate_ms": duration - first if first is not None else None,
                        "reasoning_tokens": (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"),
                        "reasoning_chars": body.get("reasoning_chars")})
        raw = body.get("content") or ""
        cleaned = raw.strip()
        if cleaned.startswith(CODE_FENCE):  # some models wrap JSON in a code fence despite response_format
            cleaned = cleaned.strip("`").removeprefix("json").strip()
        try:
            parsed = json.loads(cleaned or "{}")
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
    if provider == "openrouter":
        return OpenRouterClient()
    if provider in {"none", "off", "disabled"}:
        return DisabledLLMClient()
    raise ValueError(f"Unknown MEDIROUTE_LLM_PROVIDER '{provider}': use 'ollama', 'openrouter' or 'none'")
