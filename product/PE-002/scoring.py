"""PE-002's statistics: accuracy, the paired test, the cluster bootstrap, and Holm.

Pure functions. CLAUDE.md: "Write tests for anything that computes a metric. A wrong metric
silently invalidates every experiment that uses it." Everything here is reachable from a test with
fabricated inputs, and the exact-McNemar implementation is the same one the plan's Appendix A used
for its power table, so the design and the analysis cannot drift apart.
"""

from __future__ import annotations

import math
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Sequence


@dataclass(frozen=True)
class Scored:
    """One scored item: which conversation it came from, and whether each system got it right."""

    item_id: str
    conversation_id: str
    correct: bool


def accuracy(correct: Sequence[bool]) -> float:
    return (sum(1 for c in correct if c) / len(correct)) if correct else 0.0


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval. Reported beside the bootstrap, never as the headline.

    It assumes independent items, which `(message, turn)` rows from a few dozen conversations are
    not, so it is systematically too narrow here. That is exactly why it is not the headline.
    """
    if n == 0:
        return (0.0, 1.0)
    p = k / n
    d = 1 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return ((centre - half) / d, (centre + half) / d)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar on the discordant pairs.

    `b` is the count where the baseline was wrong and the candidate right; `c` the reverse. The
    concordant pairs carry no information about a difference and are not used, which is the whole
    point of pairing. Identical to the implementation in the plan's Appendix A, so the power table
    that justified the 10 pp threshold describes this test and not a different one.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


@dataclass(frozen=True)
class PairedResult:
    baseline_accuracy: float
    candidate_accuracy: float
    difference_pp: float
    b_baseline_wrong_candidate_right: int
    c_baseline_right_candidate_wrong: int
    discordant: int
    p_value: float

    def as_dict(self) -> dict[str, float | int]:
        return {
            "baseline_accuracy": round(self.baseline_accuracy, 4),
            "candidate_accuracy": round(self.candidate_accuracy, 4),
            "difference_pp": round(self.difference_pp, 2),
            "b_baseline_wrong_candidate_right": self.b_baseline_wrong_candidate_right,
            "c_baseline_right_candidate_wrong": self.c_baseline_right_candidate_wrong,
            "discordant": self.discordant,
            # NOT rounded. A strongly significant exact test gives a p-value of order 1e-11, and
            # rounding it to six places prints "0.0", which reads as an impossible exactness. JSON
            # carries the float as it is.
            "p_value": self.p_value,
        }


def paired_compare(baseline: Sequence[Scored], candidate: Sequence[Scored]) -> PairedResult:
    """Compare two systems on the same items, paired by item id.

    Raises if the two do not cover exactly the same items: an unpaired comparison computed as a
    paired one would silently report the wrong test, and there is no sensible way to guess which
    items to drop.
    """
    base = {s.item_id: s.correct for s in baseline}
    cand = {s.item_id: s.correct for s in candidate}
    if set(base) != set(cand):
        missing = len(set(base) ^ set(cand))
        raise ValueError(
            f"paired_compare needs the same items on both sides; {missing} item(s) differ"
        )
    b = sum(1 for k in base if not base[k] and cand[k])
    c = sum(1 for k in base if base[k] and not cand[k])
    acc_b = accuracy([base[k] for k in base])
    acc_c = accuracy([cand[k] for k in base])
    return PairedResult(
        baseline_accuracy=acc_b,
        candidate_accuracy=acc_c,
        difference_pp=(acc_c - acc_b) * 100.0,
        b_baseline_wrong_candidate_right=b,
        c_baseline_right_candidate_wrong=c,
        discordant=b + c,
        p_value=mcnemar_exact(b, c),
    )


def cluster_bootstrap(
    scored: Sequence[Scored],
    statistic: Callable[[Sequence[Scored]], float],
    *,
    resamples: int,
    seed: int,
) -> dict[str, float | int]:
    """Percentile interval from resampling CONVERSATIONS with replacement, not items.

    Resampling items would treat five rows from one conversation as five independent observations
    and give an interval that is too narrow. Conversations are the cluster, as EXP-003's Metric
    already requires for the same reason.

    A resample that draws no usable items yields no statistic; those are excluded from the
    percentiles and counted, the way EXP-000 pre-registered for undefined replicates. Above 5%
    undefined the interval itself is marked not interpretable rather than quietly narrowed.
    """
    by_conv: dict[str, list[Scored]] = defaultdict(list)
    for s in scored:
        by_conv[s.conversation_id].append(s)
    conversations = sorted(by_conv)
    if not conversations:
        return {"point": 0.0, "lo": 0.0, "hi": 1.0, "undefined_resamples": resamples,
                "interpretable": False, "n_clusters": 0}

    rng = random.Random(seed)
    values: list[float] = []
    undefined = 0
    for _ in range(resamples):
        drawn: list[Scored] = []
        for _ in range(len(conversations)):
            drawn.extend(by_conv[conversations[rng.randrange(len(conversations))]])
        if not drawn:
            undefined += 1
            continue
        values.append(statistic(drawn))

    if not values:
        return {"point": statistic(scored), "lo": 0.0, "hi": 1.0,
                "undefined_resamples": undefined, "interpretable": False,
                "n_clusters": len(conversations)}

    values.sort()
    lo = values[int(0.025 * (len(values) - 1))]
    hi = values[int(math.ceil(0.975 * (len(values) - 1)))]
    return {
        "point": round(statistic(scored), 4),
        "lo": round(lo, 4),
        "hi": round(hi, 4),
        "width_pp": round((hi - lo) * 100, 2),
        "undefined_resamples": undefined,
        "interpretable": (undefined / resamples) <= 0.05,
        "n_clusters": len(conversations),
    }


def accuracy_of(scored: Sequence[Scored]) -> float:
    return accuracy([s.correct for s in scored])


def holm(p_values: dict[str, float]) -> dict[str, float]:
    """Holm-Bonferroni adjusted p-values, for the secondary pairings.

    Seven rungs make 21 pairings; running them all at 0.05 would be expected to produce a
    "significant" difference from nothing. The primary comparison per Gate 2 condition is named in
    PE-002's Metric and is NOT part of this family.

    Adjusted values are made monotonic, so a later test's adjustment is never smaller than an
    earlier one's, and each is capped at 1.
    """
    if not p_values:
        return {}
    ordered = sorted(p_values.items(), key=lambda kv: kv[1])
    m = len(ordered)
    out: dict[str, float] = {}
    running = 0.0
    for i, (name, p) in enumerate(ordered):
        adjusted = min(1.0, (m - i) * p)
        running = max(running, adjusted)
        out[name] = round(running, 6)
    return out


def spread(values: Sequence[float]) -> dict[str, float]:
    """Mean and spread over repeated runs. CLAUDE.md requires both whenever a model is sampled."""
    vals = list(values)
    if not vals:
        return {"mean": 0.0, "min": 0.0, "max": 0.0, "stdev": 0.0, "n": 0}
    return {
        "mean": round(statistics.fmean(vals), 4),
        "min": round(min(vals), 4),
        "max": round(max(vals), 4),
        "stdev": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
        "n": len(vals),
    }
