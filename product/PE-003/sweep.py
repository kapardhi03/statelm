"""The training loop, the early stopping, and the learning-rate sweep.

The order is pre-registered and the order is the point: 3 LRs x 3 seeds, each run early-stopped on
**dev** accuracy; the LR chosen by mean dev accuracy across its three seeds; and only then the
three checkpoints at that LR scored on test, once. Nothing is ever selected on test — not the
checkpoint, not the LR, not the configuration.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from dataset import MaskedExample
from recipe import (
    BASE_LR,
    BATCH_SIZE,
    EARLY_STOPPING_PATIENCE,
    LR_SWEEP_FACTORS,
    MAX_EPOCHS,
    SEEDS,
)

# Takes a sampler and returns dev accuracy in [0, 1]. Injected so tests can script a curve.
DevEvaluator = Callable[[Any], float]


@dataclass
class EpochRecord:
    epoch: int
    mean_loss: float
    dev_accuracy: float
    checkpoint: str


@dataclass
class RunResult:
    learning_rate: float
    seed: int
    epochs: list[EpochRecord] = field(default_factory=list)
    best_epoch: int = 0
    best_dev_accuracy: float = 0.0
    best_checkpoint: str = ""
    stopped_early: bool = False
    tokens_trained: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "learning_rate": self.learning_rate,
            "seed": self.seed,
            "best_epoch": self.best_epoch,
            "best_dev_accuracy": round(self.best_dev_accuracy, 4),
            "best_checkpoint": self.best_checkpoint,
            "stopped_early": self.stopped_early,
            "epochs_run": len(self.epochs),
            "tokens_trained": self.tokens_trained,
            # The dev curve, so a reader can see whether early stopping fired on a plateau or on
            # a decline — the difference between "it had converged" and "it was overfitting".
            "dev_curve": [round(e.dev_accuracy, 4) for e in self.epochs],
            "loss_curve": [round(e.mean_loss, 4) for e in self.epochs],
        }


def batches(examples: list[MaskedExample], size: int, seed: int) -> list[list[MaskedExample]]:
    """Shuffle under the seed, then split into batches. The last batch may be short."""
    shuffled = list(examples)
    random.Random(seed).shuffle(shuffled)
    return [shuffled[i : i + size] for i in range(0, len(shuffled), size)]


def train_one(
    backend: Any,
    examples: list[MaskedExample],
    *,
    learning_rate: float,
    seed: int,
    evaluate_dev: DevEvaluator,
    max_epochs: int = MAX_EPOCHS,
    patience: int = EARLY_STOPPING_PATIENCE,
    batch_size: int = BATCH_SIZE,
) -> RunResult:
    """One training run: epochs until dev stops improving, then the best-dev checkpoint.

    The checkpoint kept is the one with the best **dev** accuracy, not the last one and not the best
    test one. Patience counts evaluations without an improvement, so a plateau ends the run rather
    than burning the remaining epochs.
    """
    result = RunResult(learning_rate=learning_rate, seed=seed)
    since_improvement = 0

    for epoch in range(1, max_epochs + 1):
        losses: list[float] = []
        for batch in batches(examples, batch_size, seed + epoch):
            losses.append(backend.train_batch(batch, learning_rate=learning_rate))
        name = f"lr{learning_rate:.2e}-seed{seed}-epoch{epoch}"
        sampler = backend.checkpoint(name)
        dev_accuracy = evaluate_dev(sampler)
        mean_loss = sum(losses) / len(losses) if losses else 0.0
        result.epochs.append(EpochRecord(epoch, mean_loss, dev_accuracy, name))

        if dev_accuracy > result.best_dev_accuracy or result.best_checkpoint == "":
            result.best_dev_accuracy = dev_accuracy
            result.best_epoch = epoch
            result.best_checkpoint = name
            since_improvement = 0
        else:
            since_improvement += 1
            if since_improvement >= patience:
                result.stopped_early = True
                break

    result.tokens_trained = backend.tokens_trained()
    return result


@dataclass
class SweepResult:
    runs: list[RunResult]
    chosen_learning_rate: float
    dev_means: dict[str, float]

    def as_dict(self) -> dict[str, Any]:
        return {
            "chosen_learning_rate": self.chosen_learning_rate,
            # What the choice was made from, so the selection is auditable rather than asserted.
            "dev_mean_by_learning_rate": {k: round(v, 4) for k, v in sorted(self.dev_means.items())},
            "runs": [r.as_dict() for r in self.runs],
        }

    def runs_at_chosen_lr(self) -> list[RunResult]:
        """The seeds trained at the chosen learning rate.

        Matched with `isclose`, not `==`. An earlier version selected the learning rate by
        formatting it to a string and parsing it back, so `base_lr * (1/3)` became `3.33e-05` and
        matched nothing: the sweep would choose a learning rate and then score **zero** seeds on
        test, producing an empty result rather than failing. Caught by
        `test_runs_at_chosen_lr_are_sorted_by_seed`.
        """
        return sorted(
            (
                r
                for r in self.runs
                if math.isclose(r.learning_rate, self.chosen_learning_rate, rel_tol=1e-12)
            ),
            key=lambda r: r.seed,
        )


def run_sweep(
    make_backend: Callable[[float, int], Any],
    make_examples: Callable[[Any], list[MaskedExample]],
    *,
    evaluate_dev: Callable[[Any, Any], float],
    base_lr: float = BASE_LR,
    factors: Sequence[float] = LR_SWEEP_FACTORS,
    seeds: Sequence[int] = SEEDS,
    max_epochs: int = MAX_EPOCHS,
) -> SweepResult:
    """3 LRs x 3 seeds, then choose the LR by mean dev accuracy across its seeds.

    `make_backend(lr, seed)` returns a fresh backend per run: a run that continued from the
    previous one's weights would not be an independent seed. `make_examples(backend)` tokenises
    against that backend's tokenizer, which is why it is a callable rather than a list.
    """
    runs: list[RunResult] = []
    for factor in factors:
        lr = base_lr * factor
        for seed in seeds:
            backend = make_backend(lr, seed)
            examples = make_examples(backend)
            runs.append(
                train_one(
                    backend,
                    examples,
                    learning_rate=lr,
                    seed=seed,
                    evaluate_dev=lambda sampler, _b=backend: evaluate_dev(_b, sampler),
                    max_epochs=max_epochs,
                )
            )

    # The learning rates stay FLOATS throughout. Selecting by a formatted label and parsing it
    # back is what produced the empty-result bug described in runs_at_chosen_lr.
    lrs = [base_lr * f for f in factors]
    means: dict[float, float] = {}
    for lr in lrs:
        at_lr = [
            r.best_dev_accuracy
            for r in runs
            if math.isclose(r.learning_rate, lr, rel_tol=1e-12)
        ]
        means[lr] = sum(at_lr) / len(at_lr) if at_lr else 0.0

    # Ties break on the lower learning rate, so the choice is deterministic rather than dependent
    # on dict order.
    chosen = max(lrs, key=lambda lr: (means[lr], -lr))
    return SweepResult(
        runs=runs,
        chosen_learning_rate=chosen,
        dev_means={f"{lr:.3e}": means[lr] for lr in lrs},
    )
