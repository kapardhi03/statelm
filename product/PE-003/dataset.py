"""Training examples, and the loss-mask check that catches the silent failure.

PE-003's Setup pre-registered this, and it is the most important thing in this directory:

> Only the completion tokens carry weight 1; every prompt token is masked to 0. Get it wrong and
> the model is trained to predict the conversation, the loss curve looks healthy, and the result is
> a useless model that nothing in the metrics would flag. So: **pre-registered check — the number
> of weight-1 tokens in each training example must equal the tokenised completion length, asserted
> per example, and the totals written into the run config.** A run whose weighted-token count does
> not match stops rather than trains.

The `Datum` shape follows Tinker's own "Prepare training data" reference, read 2026-11-09: position
`i` of the input predicts token `i + 1`, so the input is the full sequence minus its last token, the
targets are the full sequence minus its first, and the weights are
`[0.0] * (len(prompt) - 1) + [1.0] * len(completion)`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, Sequence


class Tokenizer(Protocol):
    def encode(self, text: str) -> list[int]: ...
    def decode(self, tokens: Sequence[int]) -> str: ...


class MaskError(AssertionError):
    """Raised when an example's loss mask does not match its completion. The run stops."""


@dataclass(frozen=True)
class Example:
    """One training example, before tokenisation."""

    item_id: str
    conversation_id: str
    prompt: str
    completion: str


@dataclass(frozen=True)
class MaskedExample:
    """A tokenised example and its loss weights, with the counts the check asserts on."""

    item_id: str
    input_tokens: list[int]
    target_tokens: list[int]
    weights: list[float]

    @property
    def n_weighted(self) -> int:
        return sum(1 for w in self.weights if w > 0.0)

    @property
    def n_positions(self) -> int:
        return len(self.weights)


def build_masked_example(
    example: Example, tokenizer: Tokenizer, *, strict: bool = True
) -> MaskedExample:
    """Tokenise one example and build its shifted inputs, targets and weights.

    Four invariants are checked, not assumed. Each one is a way a mis-masked run could look healthy:

    1. the weights, targets and inputs are all the same length;
    2. that length is `len(full_sequence) - 1`, which is what the one-position shift requires;
    3. the number of weight-1 positions equals the tokenised completion length — the pre-registered
       check;
    4. every weight-1 position is at the END of the sequence, so the mask cannot be inverted or
       scattered while still having the right *count*.

    (4) is not in the record and is Claude Code's addition: a mask with the right number of ones in
    the wrong places passes (3) and trains on the conversation anyway.
    """
    prompt_tokens = tokenizer.encode(example.prompt)
    completion_tokens = tokenizer.encode(example.completion)
    if not prompt_tokens:
        raise MaskError(f"{example.item_id}: the prompt tokenised to nothing")
    if not completion_tokens:
        raise MaskError(f"{example.item_id}: the completion tokenised to nothing")

    full = prompt_tokens + completion_tokens
    n_prefix = len(prompt_tokens) - 1
    weights = [0.0] * n_prefix + [1.0] * len(completion_tokens)
    masked = MaskedExample(
        item_id=example.item_id,
        input_tokens=full[:-1],
        target_tokens=full[1:],
        weights=weights,
    )

    if not strict:
        return masked

    if not (len(masked.weights) == len(masked.target_tokens) == len(masked.input_tokens)):
        raise MaskError(
            f"{example.item_id}: inputs, targets and weights differ in length "
            f"({len(masked.input_tokens)}, {len(masked.target_tokens)}, {len(masked.weights)})"
        )
    if masked.n_positions != len(full) - 1:
        raise MaskError(
            f"{example.item_id}: {masked.n_positions} positions for a {len(full)}-token sequence; "
            "the one-position shift requires len(sequence) - 1"
        )
    if masked.n_weighted != len(completion_tokens):
        raise MaskError(
            f"{example.item_id}: {masked.n_weighted} weighted positions but the completion is "
            f"{len(completion_tokens)} tokens. PE-003's pre-registered check: a mis-masked run "
            "trains the model to predict the conversation and the loss curve looks healthy. "
            "Nothing has been trained."
        )
    tail = masked.weights[-len(completion_tokens) :]
    if any(w <= 0.0 for w in tail) or any(w > 0.0 for w in masked.weights[: -len(completion_tokens)]):
        raise MaskError(
            f"{example.item_id}: the weighted positions are not the last "
            f"{len(completion_tokens)} of the sequence. The count is right and the placement is "
            "not, which trains on the conversation anyway. Nothing has been trained."
        )
    return masked


def build_dataset(
    examples: list[Example], tokenizer: Tokenizer
) -> tuple[list[MaskedExample], dict[str, Any]]:
    """Tokenise every example, and return the totals the run config records."""
    if not examples:
        raise ValueError("no training examples: the train split is empty or unlabelled")
    masked = [build_masked_example(e, tokenizer) for e in examples]
    weighted = sum(m.n_weighted for m in masked)
    positions = sum(m.n_positions for m in masked)
    return masked, {
        "n_examples": len(masked),
        "weighted_tokens_total": weighted,
        "positions_total": positions,
        # The share of positions that carry loss. On a classification target with a long
        # conversation in the prompt this is small, and a value near 1.0 would mean the mask is
        # not doing its job — worth having in the config rather than inferring it later.
        "weighted_share": round(weighted / positions, 6) if positions else 0.0,
        "tokens_per_example_mean": round(positions / len(masked), 2),
    }


def to_datum(masked: MaskedExample, types_module: Any) -> Any:
    """Build a Tinker `Datum`. The module is injected so tests need no SDK.

    Shape from Tinker's "Prepare training data" reference, read 2026-11-09.
    """
    return types_module.Datum(
        model_input=types_module.ModelInput.from_ints(tokens=masked.input_tokens),
        loss_fn_inputs=dict(weights=masked.weights, target_tokens=masked.target_tokens),
    )
