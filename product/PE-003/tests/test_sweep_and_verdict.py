"""The sweep, the early stopping, the dev selection, and the pre-registered verdict."""

from __future__ import annotations

import pytest

from dataset import Example, build_dataset
from run_finetune import verdict
from sweep import batches, run_sweep, train_one
from recipe import ALPHA, LR_SWEEP_FACTORS, MIN_EFFECT_PP, PRIMARY_SEED, SEEDS
from trainer import StubBackend, StubTokenizer


def _examples(n: int = 16):
    tok = StubTokenizer()
    raw = [Example(f"it-{i}", f"c{i // 4}", f"prompt {i} with some words", "ask_budget")
           for i in range(n)]
    masked, _ = build_dataset(raw, tok)
    return masked


# --- batching -------------------------------------------------------------------------------------

def test_batches_cover_every_example_once():
    ex = _examples(10)
    out = batches(ex, 4, seed=0)
    assert sum(len(b) for b in out) == 10
    assert {e.item_id for b in out for e in b} == {e.item_id for e in ex}


def test_batches_are_deterministic_under_a_seed():
    ex = _examples(10)
    a = [[e.item_id for e in b] for b in batches(ex, 4, seed=1)]
    b = [[e.item_id for e in b] for b in batches(ex, 4, seed=1)]
    assert a == b


def test_batches_differ_under_a_different_seed():
    ex = _examples(10)
    a = [[e.item_id for e in b] for b in batches(ex, 4, seed=1)]
    b = [[e.item_id for e in b] for b in batches(ex, 4, seed=2)]
    assert a != b


# --- early stopping and checkpoint selection ------------------------------------------------------

def _curve_evaluator(values):
    """A dev curve, one value per evaluation."""
    seen = {"n": 0}

    def evaluate(_sampler):
        i = min(seen["n"], len(values) - 1)
        seen["n"] += 1
        return values[i]

    return evaluate


def test_early_stopping_fires_on_a_plateau():
    """Patience counts evaluations without an improvement, so a plateau ends the run."""
    r = train_one(
        StubBackend(), _examples(), learning_rate=1e-4, seed=0,
        evaluate_dev=_curve_evaluator([0.5, 0.5, 0.5, 0.5]), max_epochs=10, patience=2,
    )
    assert r.stopped_early is True
    assert len(r.epochs) == 3, "first sets the best, then two without improvement"


def test_the_kept_checkpoint_is_the_best_dev_one_not_the_last():
    r = train_one(
        StubBackend(), _examples(), learning_rate=1e-4, seed=0,
        evaluate_dev=_curve_evaluator([0.4, 0.8, 0.6, 0.5]), max_epochs=10, patience=2,
    )
    assert r.best_epoch == 2
    assert r.best_dev_accuracy == pytest.approx(0.8)
    assert "epoch2" in r.best_checkpoint
    assert len(r.epochs) == 4, "two evaluations after the best, then it stops"


def test_a_rising_curve_runs_to_the_epoch_cap():
    r = train_one(
        StubBackend(), _examples(), learning_rate=1e-4, seed=0,
        evaluate_dev=_curve_evaluator([0.1, 0.2, 0.3, 0.4, 0.5]), max_epochs=4, patience=2,
    )
    assert r.stopped_early is False
    assert len(r.epochs) == 4
    assert r.best_epoch == 4


def test_the_learning_rate_reaches_the_optimizer():
    backend = StubBackend()
    train_one(backend, _examples(), learning_rate=3e-4, seed=0,
              evaluate_dev=_curve_evaluator([0.5, 0.5, 0.5]), max_epochs=3, patience=2)
    assert set(backend.learning_rates) == {3e-4}


def test_the_dev_curve_is_recorded():
    """So a reader can tell early stopping on a plateau from early stopping on a decline."""
    r = train_one(
        StubBackend(), _examples(), learning_rate=1e-4, seed=0,
        evaluate_dev=_curve_evaluator([0.8, 0.6, 0.4]), max_epochs=10, patience=2,
    )
    assert r.as_dict()["dev_curve"] == [0.8, 0.6, 0.4]


# --- the sweep ------------------------------------------------------------------------------------

def test_sweep_runs_every_learning_rate_and_seed():
    runs = []

    def make_backend(lr, seed):
        b = StubBackend(name=f"{lr}-{seed}")
        runs.append(b)
        return b

    result = run_sweep(
        make_backend,
        lambda _b: _examples(),
        evaluate_dev=lambda _b, _s: 0.5,
        max_epochs=2,
    )
    assert len(result.runs) == len(LR_SWEEP_FACTORS) * len(SEEDS)
    assert len(runs) == len(LR_SWEEP_FACTORS) * len(SEEDS), "a fresh backend per run"


def test_each_run_gets_a_fresh_backend():
    """A run continuing from the previous one's weights would not be an independent seed."""
    made = []
    run_sweep(
        lambda lr, seed: made.append(StubBackend()) or made[-1],
        lambda _b: _examples(),
        evaluate_dev=lambda _b, _s: 0.5,
        max_epochs=1,
    )
    assert len(made) == len(set(id(b) for b in made))


def test_the_learning_rate_is_chosen_by_mean_dev_accuracy():
    """And by dev, never by test."""
    base = 1e-4

    def evaluate(backend, _sampler):
        # the middle factor wins
        return 0.9 if "1.00e-04" in backend.name else 0.3

    result = run_sweep(
        lambda lr, seed: StubBackend(name=f"{lr:.2e}-{seed}"),
        lambda _b: _examples(),
        evaluate_dev=evaluate,
        base_lr=base,
        max_epochs=2,
    )
    assert result.chosen_learning_rate == pytest.approx(base)
    assert len(result.runs_at_chosen_lr()) == len(SEEDS)


def test_a_non_terminating_factor_still_finds_its_runs():
    """base_lr * (1/3) cannot survive a round trip through a formatted label.

    An earlier version selected the learning rate that way, so the lowest factor matched no runs
    and the sweep returned a chosen LR with zero seeds to score — an empty result rather than a
    failure. This pins the case directly.
    """
    base = 1e-4

    def evaluate(backend, _sampler):
        return 0.9 if "3.33e-05" in backend.name else 0.2

    result = run_sweep(
        lambda lr, seed: StubBackend(name=f"{lr:.2e}-{seed}"),
        lambda _b: _examples(),
        evaluate_dev=evaluate,
        base_lr=base,
        max_epochs=1,
    )
    assert result.chosen_learning_rate == pytest.approx(base / 3)
    assert len(result.runs_at_chosen_lr()) == len(SEEDS), "the chosen LR must find its own runs"


def test_sweep_records_what_the_choice_was_made_from():
    result = run_sweep(
        lambda lr, seed: StubBackend(),
        lambda _b: _examples(),
        evaluate_dev=lambda _b, _s: 0.5,
        max_epochs=1,
    )
    d = result.as_dict()
    assert len(d["dev_mean_by_learning_rate"]) == len(LR_SWEEP_FACTORS)
    assert d["chosen_learning_rate"] in [r.learning_rate for r in result.runs]


def test_runs_at_chosen_lr_are_sorted_by_seed():
    result = run_sweep(
        lambda lr, seed: StubBackend(),
        lambda _b: _examples(),
        evaluate_dev=lambda _b, _s: 0.5,
        max_epochs=1,
    )
    seeds = [r.seed for r in result.runs_at_chosen_lr()]
    assert seeds == sorted(seeds) == list(SEEDS)


# --- the verdict ----------------------------------------------------------------------------------

def _seed_body(diff_pp: float, p: float) -> dict:
    return {"difference_pp": diff_pp, "p_value": p}


def test_passes_when_seed_zero_clears_both_and_the_seeds_agree():
    v = verdict(
        {0: _seed_body(15.0, 0.001), 1: _seed_body(14.0, 0.002), 2: _seed_body(20.0, 0.0001)},
        primary_seed=PRIMARY_SEED,
    )
    assert v["verdict"] == "PASS"
    assert v["seeds_agree"] is True


def test_fails_when_the_effect_is_below_the_threshold():
    v = verdict(
        {0: _seed_body(6.0, 0.001), 1: _seed_body(5.0, 0.002), 2: _seed_body(4.0, 0.01)},
        primary_seed=PRIMARY_SEED,
    )
    assert v["verdict"] == "FAIL"


def test_fails_when_the_effect_is_large_but_not_significant():
    v = verdict(
        {0: _seed_body(15.0, 0.4), 1: _seed_body(16.0, 0.3), 2: _seed_body(14.0, 0.5)},
        primary_seed=PRIMARY_SEED,
    )
    assert v["verdict"] == "FAIL"


def test_unstable_when_the_seeds_disagree():
    """A spread that can flip the answer has swamped the effect. No claim either way."""
    v = verdict(
        {0: _seed_body(15.0, 0.001), 1: _seed_body(3.0, 0.4), 2: _seed_body(16.0, 0.002)},
        primary_seed=PRIMARY_SEED,
    )
    assert v["verdict"] == "UNSTABLE"
    assert v["seeds_agree"] is False


def test_unstable_even_when_the_primary_seed_fails():
    """Instability is not resolved by which way seed 0 happened to land."""
    v = verdict(
        {0: _seed_body(2.0, 0.6), 1: _seed_body(15.0, 0.001), 2: _seed_body(16.0, 0.002)},
        primary_seed=PRIMARY_SEED,
    )
    assert v["verdict"] == "UNSTABLE"


def test_the_primary_seed_decides_not_the_majority():
    """Seed 0 is named in advance; a vote would be choosing after the fact."""
    v = verdict(
        {0: _seed_body(15.0, 0.001), 1: _seed_body(15.0, 0.001), 2: _seed_body(15.0, 0.001)},
        primary_seed=PRIMARY_SEED,
    )
    assert v["primary_seed"] == 0


def test_verdict_carries_the_thresholds_it_applied():
    v = verdict({0: _seed_body(15.0, 0.001)}, primary_seed=PRIMARY_SEED)
    assert v["threshold_pp"] == MIN_EFFECT_PP
    assert v["alpha"] == ALPHA


def test_no_seeds_is_not_established():
    assert verdict({}, primary_seed=PRIMARY_SEED)["verdict"] == "NOT_ESTABLISHED"
