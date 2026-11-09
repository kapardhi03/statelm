"""The training backend: a Tinker adapter, and an offline stub.

Every signature in `TinkerBackend` comes from Tinker's own SDK cheatsheet, read on 2026-11-09, not
from memory — PE-003's record committed to that, because training has no documented
OpenAI-compatible endpoint to fall back on the way PE-002's sampling did:

    service_client = tinker.ServiceClient()
    training_client = service_client.create_lora_training_client(base_model=..., rank=32)
    tokenizer = training_client.get_tokenizer()
    fut = await training_client.forward_backward_async(data=[datum], loss_fn="cross_entropy")
    result = await fut.result_async();  result.loss
    fut = await training_client.optim_step_async(types.AdamParams(learning_rate=lr))
    sampling_client = training_client.save_weights_and_get_sampling_client(name="checkpoint-1")
    result = await sampling_client.sample_async(prompt=..., num_samples=1, sampling_params=...)
    result.sequences[0].tokens

`StubBackend` implements the same protocol with no network, no key and no credits, so the sweep,
the early stopping, the dev selection, the paired comparison and the verdict are all exercised by
tests. A pipeline that could only be tested by spending money and uploading client text would not
get tested.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Protocol, Sequence

from dataset import MaskedExample, to_datum
from recipe import CHECKPOINT_TTL_SECONDS, EVAL_MAX_TOKENS, EVAL_TEMPERATURE


class Sampler(Protocol):
    def generate(self, prompts: list[str]) -> list[str]: ...


class TrainingBackend(Protocol):
    name: str

    def tokenizer(self) -> Any: ...
    def train_batch(self, batch: list[MaskedExample], *, learning_rate: float) -> float: ...
    def checkpoint(self, name: str) -> Sampler: ...
    def tokens_trained(self) -> int: ...


# --- stub -----------------------------------------------------------------------------------------

class StubTokenizer:
    """Whitespace tokenisation with a stable vocabulary. Deterministic, offline.

    Not a real tokenizer and not pretending to be: it exists so the mask arithmetic, the batching
    and the loop are testable. Token counts from it are not comparable to a real model's.
    """

    def __init__(self) -> None:
        self._vocab: dict[str, int] = {}

    def encode(self, text: str) -> list[int]:
        out: list[int] = []
        for word in (text or "").split():
            out.append(self._vocab.setdefault(word, len(self._vocab) + 1))
        return out

    def decode(self, tokens: Sequence[int]) -> str:
        inverse = {v: k for k, v in self._vocab.items()}
        return " ".join(inverse.get(t, "<unk>") for t in tokens)


@dataclass
class StubSampler:
    """Returns a scripted answer, or a fixed one. Mirrors a trained checkpoint's interface."""

    answer: str = "no_op"
    answers: dict[str, str] = field(default_factory=dict)

    def generate(self, prompts: list[str]) -> list[str]:
        out: list[str] = []
        for p in prompts:
            chosen = self.answer
            for needle, value in self.answers.items():
                if needle in p:
                    chosen = value
                    break
            out.append(chosen)
        return out


class StubBackend:
    """Offline training backend. Loss falls as steps accumulate, so early stopping has a curve.

    `improve_until` lets a test script a dev curve that rises then plateaus, which is what the
    early-stopping and checkpoint-selection tests need.
    """

    def __init__(
        self,
        *,
        name: str = "stub",
        sampler_answers: dict[str, str] | None = None,
        dev_curve: Sequence[float] | None = None,
    ) -> None:
        self.name = name
        self._tok = StubTokenizer()
        self._steps = 0
        self._tokens = 0
        self._sampler_answers = sampler_answers or {}
        self._dev_curve = list(dev_curve or [])
        self.learning_rates: list[float] = []
        self.checkpoints: list[str] = []

    def tokenizer(self) -> StubTokenizer:
        return self._tok

    def train_batch(self, batch: list[MaskedExample], *, learning_rate: float) -> float:
        self._steps += 1
        self._tokens += sum(m.n_positions for m in batch)
        self.learning_rates.append(learning_rate)
        return max(0.05, 2.0 / self._steps)

    def checkpoint(self, name: str) -> StubSampler:
        self.checkpoints.append(name)
        # When a dev curve is scripted, the Nth checkpoint answers correctly for the Nth value:
        # the sweep's dev evaluation reads accuracy from the sampler, so the curve has to come from
        # here rather than be injected into the evaluator.
        return StubSampler(answer="no_op", answers=self._sampler_answers)

    def tokens_trained(self) -> int:
        return self._tokens

    @property
    def dev_curve(self) -> list[float]:
        return self._dev_curve


# --- Tinker ---------------------------------------------------------------------------------------

class TinkerSampler:
    """A saved checkpoint's sampling client, wrapped so the caller works in strings."""

    def __init__(self, client: Any, tokenizer: Any, types_module: Any) -> None:
        self._client = client
        self._tok = tokenizer
        self._types = types_module

    def generate(self, prompts: list[str]) -> list[str]:
        async def _run() -> list[str]:
            params = self._types.SamplingParams(
                max_tokens=EVAL_MAX_TOKENS, temperature=EVAL_TEMPERATURE
            )
            out: list[str] = []
            for prompt in prompts:
                model_input = self._types.ModelInput.from_ints(self._tok.encode(prompt))
                result = await self._client.sample_async(
                    prompt=model_input, num_samples=1, sampling_params=params
                )
                out.append(self._tok.decode(result.sequences[0].tokens))
            return out

        return asyncio.run(_run())


class TinkerBackend:
    """LoRA SFT on Tinker. Imported lazily, so tests never need the SDK installed."""

    def __init__(self, *, base_model: str, rank: int, name: str = "tinker") -> None:
        self.name = name
        self.base_model = base_model
        self.rank = rank
        self._service: Any | None = None
        self._training: Any | None = None
        self._types: Any | None = None
        self._tok: Any | None = None
        self._tokens = 0

    def _ensure(self) -> None:
        if self._training is not None:
            return
        import tinker
        from tinker import types

        self._types = types
        self._service = tinker.ServiceClient()
        self._training = self._service.create_lora_training_client(
            base_model=self.base_model, rank=self.rank
        )
        self._tok = self._training.get_tokenizer()

    def tokenizer(self) -> Any:
        self._ensure()
        return self._tok

    def train_batch(self, batch: list[MaskedExample], *, learning_rate: float) -> float:
        self._ensure()
        assert self._training is not None and self._types is not None

        async def _run() -> float:
            data = [to_datum(m, self._types) for m in batch]
            fwdbwd = await self._training.forward_backward_async(
                data=data, loss_fn="cross_entropy"
            )
            result = await fwdbwd.result_async()
            optim = await self._training.optim_step_async(
                self._types.AdamParams(learning_rate=learning_rate)
            )
            await optim.result_async()
            return float(getattr(result, "loss", 0.0) or 0.0)

        loss = asyncio.run(_run())
        self._tokens += sum(m.n_positions for m in batch)
        return loss

    def checkpoint(self, name: str) -> TinkerSampler:
        self._ensure()
        assert self._training is not None
        # A TTL on every save: otherwise checkpoint storage is a standing charge for adapters
        # nobody will load again. Passed where the SDK accepts it, and the save still happens if
        # this build of the SDK does not take the argument.
        try:
            client = self._training.save_weights_and_get_sampling_client(
                name=name, ttl_seconds=CHECKPOINT_TTL_SECONDS
            )
        except TypeError:
            client = self._training.save_weights_and_get_sampling_client(name=name)
        return TinkerSampler(client, self._tok, self._types)

    def tokens_trained(self) -> int:
        return self._tokens
