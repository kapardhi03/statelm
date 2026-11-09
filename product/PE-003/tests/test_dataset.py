"""The loss mask. The most important tests in this directory.

PE-003's Setup pre-registered a check here because a mis-masked run trains the model to predict the
conversation, the loss curve looks healthy, and **no metric in the experiment would catch it**.
These tests are that check's check.
"""

from __future__ import annotations

import pytest

from dataset import (
    Example,
    MaskError,
    build_dataset,
    build_masked_example,
    to_datum,
)
from trainer import StubTokenizer


@pytest.fixture
def tok() -> StubTokenizer:
    return StubTokenizer()


# --- the shape Tinker's reference requires ---------------------------------------------------------

def test_shifted_by_one_position(example, tok):
    """Position i of the input predicts token i+1, so everything is len(sequence) - 1."""
    m = build_masked_example(example, tok)
    n_prompt = len(tok.encode(example.prompt))
    n_completion = len(tok.encode(example.completion))
    assert len(m.input_tokens) == n_prompt + n_completion - 1
    assert len(m.target_tokens) == len(m.input_tokens) == len(m.weights)


def test_targets_are_the_sequence_shifted_left(example, tok):
    m = build_masked_example(example, tok)
    full = tok.encode(example.prompt) + tok.encode(example.completion)
    assert m.input_tokens == full[:-1]
    assert m.target_tokens == full[1:]


# --- the pre-registered check ---------------------------------------------------------------------

def test_weighted_positions_equal_the_completion_length(example, tok):
    m = build_masked_example(example, tok)
    assert m.n_weighted == len(tok.encode(example.completion))


def test_the_weighted_positions_are_at_the_end(example, tok):
    """A mask with the right COUNT in the wrong places trains on the conversation anyway."""
    m = build_masked_example(example, tok)
    n_completion = len(tok.encode(example.completion))
    assert all(w == 1.0 for w in m.weights[-n_completion:])
    assert all(w == 0.0 for w in m.weights[:-n_completion])


def test_an_inverted_mask_is_caught(example, tok, monkeypatch):
    """The failure the check exists for: prompt weighted, completion masked."""
    import dataset

    real = dataset.MaskedExample

    class Inverted(real):  # type: ignore[misc,valid-type]
        pass

    def inverted_builder(ex, tokenizer, *, strict=True):
        prompt_tokens = tokenizer.encode(ex.prompt)
        completion_tokens = tokenizer.encode(ex.completion)
        full = prompt_tokens + completion_tokens
        bad = real(
            item_id=ex.item_id,
            input_tokens=full[:-1],
            target_tokens=full[1:],
            # right count, wrong end
            weights=[1.0] * len(completion_tokens)
            + [0.0] * (len(prompt_tokens) - 1),
        )
        return bad

    bad = inverted_builder(example, tok)
    assert bad.n_weighted == len(tok.encode(example.completion)), "count is right"
    # and yet the placement check must reject it
    with pytest.raises(MaskError, match="not the last"):
        _assert_placement(bad, len(tok.encode(example.completion)))


def _assert_placement(masked, n_completion: int) -> None:
    """The placement half of build_masked_example's contract, applied to a hand-built mask."""
    tail = masked.weights[-n_completion:]
    if any(w <= 0.0 for w in tail) or any(w > 0.0 for w in masked.weights[:-n_completion]):
        raise MaskError(
            f"{masked.item_id}: the weighted positions are not the last {n_completion}"
        )


def test_an_empty_prompt_is_refused(tok):
    with pytest.raises(MaskError, match="prompt tokenised to nothing"):
        build_masked_example(Example("x", "c", "", "ask_budget"), tok)


def test_an_empty_completion_is_refused(tok):
    with pytest.raises(MaskError, match="completion tokenised to nothing"):
        build_masked_example(Example("x", "c", "a prompt", ""), tok)


def test_a_single_token_prompt_works(tok):
    """n_prefix is len(prompt) - 1, which is 0 here. The arithmetic must still hold."""
    m = build_masked_example(Example("x", "c", "word", "label"), tok)
    assert m.n_weighted == 1
    assert m.n_positions == 1


# --- the totals the run config carries ------------------------------------------------------------

def test_build_dataset_reports_its_totals(tok):
    examples = [
        Example(f"it-{n}", "c", f"prompt number {n} with words", "ask_budget") for n in range(5)
    ]
    masked, totals = build_dataset(examples, tok)
    assert len(masked) == 5
    assert totals["n_examples"] == 5
    assert totals["weighted_tokens_total"] == sum(m.n_weighted for m in masked)
    assert totals["positions_total"] == sum(m.n_positions for m in masked)


def test_weighted_share_is_small_for_a_classification_target(tok):
    """A share near 1.0 would mean the mask is not doing its job."""
    examples = [
        Example("it-2", "c", " ".join(f"w{i}" for i in range(50)), "ask_budget")
    ]
    _, totals = build_dataset(examples, tok)
    assert 0 < totals["weighted_share"] < 0.1


def test_build_dataset_refuses_an_empty_train_split(tok):
    with pytest.raises(ValueError, match="no training examples"):
        build_dataset([], tok)


# --- the Datum hand-off ---------------------------------------------------------------------------

class FakeTypes:
    """Mimics the two `tinker.types` entry points the Datum shape uses."""

    class ModelInput:
        def __init__(self, tokens): self.tokens = tokens
        @classmethod
        def from_ints(cls, tokens): return cls(tokens)

    class Datum:
        def __init__(self, model_input, loss_fn_inputs):
            self.model_input = model_input
            self.loss_fn_inputs = loss_fn_inputs


def test_to_datum_matches_tinkers_documented_shape(example, tok):
    m = build_masked_example(example, tok)
    d = to_datum(m, FakeTypes)
    assert d.model_input.tokens == m.input_tokens
    assert d.loss_fn_inputs["weights"] == m.weights
    assert d.loss_fn_inputs["target_tokens"] == m.target_tokens
    assert set(d.loss_fn_inputs) == {"weights", "target_tokens"}
