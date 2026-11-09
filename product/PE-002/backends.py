"""Model backends for stage 2. Thin adapters, one per API shape.

Three of them:

- **StubBackend** — deterministic, no network. Every test uses it, so the whole stage-2 pipeline is
  testable without a key, a credit or an upload.
- **AnthropicBackend** — the official `anthropic` SDK, for a frontier rung.
- **OpenAICompatibleBackend** — the official `openai` SDK against a configurable `base_url`. This
  covers both a second frontier vendor and **the Qwen rungs**, because Tinker exposes
  OpenAI-compatible inference. Using a documented compatible endpoint rather than guessing at the
  Tinker sampling SDK's signatures keeps this file honest; PE-003, which trains rather than samples,
  will use Tinker's own training API.

Two things the Claude API reference settled, and both contradict what PE-002's Setup
pre-registered. They are recorded in PE-002's Change log rather than worked around:

1. **`temperature` cannot be set on current Claude models** — sampling parameters return a 400. The
   pre-registered "greedy, temperature 0" is therefore unreachable on a Claude rung. The nearest
   equivalent for a classification task is `output_config: {effort: "low"}`.
2. **Thinking cannot be disabled on `claude-opus-5-5`** — `{type: "disabled"}` is a 400 at every
   effort level. The pre-registered "thinking disabled, and recorded in the config: a thinking and
   a non-thinking run are not the same system" cannot hold on that rung either.

Both mean a Claude rung is not strictly comparable to a Qwen rung on the decoding axis, and that
its spread across repeated runs is not controllable the way the others' is. Every completion
therefore records what was *actually* sent, not what was asked for.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

# Classification. The Claude API reference's guidance for this shape of task; large enough for a
# class name and a short wrapper, small enough that a runaway response cannot cost real money.
DEFAULT_MAX_TOKENS = 256


@dataclass
class Completion:
    text: str
    input_tokens: int
    output_tokens: int
    latency_ms: float
    # What was actually sent, including any pre-registered setting the provider refused. Goes into
    # the run config, so a later reader sees the real configuration rather than the intended one.
    settings_sent: dict[str, Any] = field(default_factory=dict)
    unsupported_settings: list[str] = field(default_factory=list)


class Backend(Protocol):
    name: str
    provider: str
    model: str

    def complete(self, prompt: str, *, constrain_to: list[str] | None) -> Completion: ...


# --- stub -----------------------------------------------------------------------------------------

class StubBackend:
    """Deterministic, offline. Returns a scripted answer per prompt, else a fixed fallback.

    Exists so that the rung loop, the cost accounting, the Gate 2 evaluation and the consent gate
    are all exercised by tests without a key or an upload. A stage-2 pipeline that could only be
    tested by spending money would not get tested.
    """

    provider = "stub"

    def __init__(
        self,
        *,
        name: str = "stub",
        model: str = "stub-model",
        answers: dict[str, str] | None = None,
        fallback: str = "unknown_action",
        tokens: tuple[int, int] = (100, 5),
    ) -> None:
        self.name = name
        self.model = model
        self._answers = answers or {}
        self._fallback = fallback
        self._tokens = tokens
        self.calls: list[str] = []

    def complete(self, prompt: str, *, constrain_to: list[str] | None) -> Completion:
        self.calls.append(prompt)
        answer = self._fallback
        for needle, value in self._answers.items():
            if needle in prompt:
                answer = value
                break
        if constrain_to and answer not in constrain_to:
            # A constrained backend cannot emit an out-of-vocabulary answer. Mirroring that here
            # keeps the B2 rung's behaviour in tests the same shape as in reality.
            answer = sorted(constrain_to)[0]
        return Completion(
            text=answer,
            input_tokens=self._tokens[0],
            output_tokens=self._tokens[1],
            latency_ms=0.0,
            settings_sent={"backend": "stub", "constrained": bool(constrain_to)},
        )


# --- Anthropic ------------------------------------------------------------------------------------

class AnthropicBackend:
    """A frontier rung on the Claude API, via the official SDK.

    `effort` is the only depth control available: thinking cannot be disabled on `claude-opus-5-5`,
    and sampling parameters are rejected. For a classification task `low` is the right level and is
    recorded as the stand-in for the pre-registered temperature-0 setting.
    """

    provider = "anthropic"

    def __init__(
        self,
        *,
        name: str,
        model: str,
        effort: str = "low",
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_retries: int = 2,
    ) -> None:
        self.name = name
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._max_retries = max_retries
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import anthropic  # imported lazily: tests never need the SDK installed

            self._client = anthropic.Anthropic(max_retries=self._max_retries)
        return self._client

    def complete(self, prompt: str, *, constrain_to: list[str] | None) -> Completion:
        import anthropic

        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "output_config": {"effort": self.effort},
            "messages": [{"role": "user", "content": prompt}],
        }
        if constrain_to:
            # B2: the answer must come from the vocabulary. Structured outputs, not a prompt
            # instruction, which is the whole point of separating B1 from B2.
            kwargs["output_config"]["format"] = {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {"action": {"type": "string", "enum": sorted(constrain_to)}},
                    "required": ["action"],
                    "additionalProperties": False,
                },
            }

        started = time.monotonic()
        try:
            response = client.messages.create(**kwargs)
        except anthropic.NotFoundError as exc:
            raise RuntimeError(f"{self.name}: model {self.model!r} not found: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise RuntimeError(f"{self.name}: rate limited after retries: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise RuntimeError(f"{self.name}: API returned {exc.status_code}: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise RuntimeError(f"{self.name}: could not reach the API: {exc}") from exc
        latency_ms = (time.monotonic() - started) * 1000.0

        # Safeguards can decline a request with HTTP 200 and stop_reason "refusal", so stop_reason
        # is checked before content is read.
        if getattr(response, "stop_reason", None) == "refusal":
            details = getattr(response, "stop_details", None)
            category = getattr(details, "category", None) if details else None
            text = ""
            refusal = [f"refused:{category or 'unknown'}"]
        else:
            text = "".join(
                block.text for block in response.content if getattr(block, "type", "") == "text"
            )
            refusal = []

        usage = response.usage
        return Completion(
            text=text.strip(),
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            latency_ms=latency_ms,
            settings_sent={
                "backend": "anthropic",
                "model": self.model,
                "effort": self.effort,
                "max_tokens": self.max_tokens,
                "constrained": bool(constrain_to),
            },
            # Recorded on every call, because PE-002's Setup pre-registered both and neither is
            # reachable here. See this module's docstring and PE-002's Change log.
            unsupported_settings=["temperature_0", "thinking_disabled", *refusal],
        )


# --- OpenAI-compatible (a second frontier vendor, and the Qwen rungs via Tinker) ------------------

class OpenAICompatibleBackend:
    """Any endpoint that speaks the OpenAI chat-completions shape.

    Used for a second frontier vendor and for the Qwen rungs through Tinker's OpenAI-compatible
    inference. `base_url` and `api_key_env` come from `providers.yaml`, so adding an endpoint is a
    config change rather than a code change — and, because of the consent gate, a recorded decision.
    """

    def __init__(
        self,
        *,
        name: str,
        provider: str,
        model: str,
        base_url: str | None = None,
        api_key_env: str | None = None,
        temperature: float | None = 0.0,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_retries: int = 2,
        extra_body: dict[str, Any] | None = None,
    ) -> None:
        self.name = name
        self.provider = provider
        self.model = model
        self.base_url = base_url
        self.api_key_env = api_key_env
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._max_retries = max_retries
        self._extra_body = extra_body or {}
        self._client: Any | None = None

    def _ensure_client(self) -> Any:
        if self._client is None:
            import os

            from openai import OpenAI  # lazy, as above

            kwargs: dict[str, Any] = {"max_retries": self._max_retries}
            if self.base_url:
                kwargs["base_url"] = self.base_url
            if self.api_key_env:
                key = os.environ.get(self.api_key_env)
                if not key:
                    raise RuntimeError(
                        f"{self.name}: ${self.api_key_env} is not set. The run was not started."
                    )
                kwargs["api_key"] = key
            self._client = OpenAI(**kwargs)
        return self._client

    def complete(self, prompt: str, *, constrain_to: list[str] | None) -> Completion:
        client = self._ensure_client()
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.temperature is not None:
            kwargs["temperature"] = self.temperature
        if self._extra_body:
            kwargs["extra_body"] = dict(self._extra_body)
        unsupported: list[str] = []
        if constrain_to:
            kwargs["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "action_choice",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string", "enum": sorted(constrain_to)}
                        },
                        "required": ["action"],
                        "additionalProperties": False,
                    },
                },
            }

        started = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
        except Exception as exc:  # the SDK's typed errors differ by endpoint; surface the message
            raise RuntimeError(f"{self.name}: request failed: {type(exc).__name__}: {exc}") from exc
        latency_ms = (time.monotonic() - started) * 1000.0

        text = (response.choices[0].message.content or "").strip()
        usage = getattr(response, "usage", None)
        return Completion(
            text=text,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
            latency_ms=latency_ms,
            settings_sent={
                "backend": "openai_compatible",
                "provider": self.provider,
                "model": self.model,
                "temperature": self.temperature,
                "max_tokens": self.max_tokens,
                "base_url_set": bool(self.base_url),
                "constrained": bool(constrain_to),
            },
            unsupported_settings=unsupported,
        )
