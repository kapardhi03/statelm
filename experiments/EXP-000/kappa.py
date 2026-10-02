"""Cohen's kappa, one-vs-rest kappa, confusion matrices and bootstrap intervals.

Pure functions over label pairs. No I/O, no CSV, no paths, so the arithmetic can be tested on
hand-checkable tables. A wrong metric silently invalidates every experiment that uses it, which
is why this is a separate module with its own tests.

A kappa is **None** when it is undefined rather than zero or one. That happens when expected
agreement is 1, which is the case where there is no variance left for chance correction to act
on: both raters used a single label, or a one-vs-rest category appears in neither rater's
column. Returning 0.0 there would read as "chance agreement" and returning 1.0 would read as
"perfect agreement"; neither is what the data says.
"""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Callable, Sequence

#: One item, as the two raters labelled it.
Pair = tuple[str, str]

IN, OUT = "in", "out"


def percent_agreement(pairs: Sequence[Pair]) -> float | None:
    if not pairs:
        return None
    return sum(1 for a, b in pairs if a == b) / len(pairs)


def cohen_kappa(pairs: Sequence[Pair]) -> float | None:
    """Two-rater Cohen's kappa. None when expected agreement is 1 (see the module docstring).

    The label set is taken from the data rather than passed in: a label with a zero marginal
    contributes nothing to expected agreement, so the observed union gives the same answer as
    the full vocabulary and cannot disagree with the data.
    """
    n = len(pairs)
    if n == 0:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    count_a, count_b = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum((count_a[k] / n) * (count_b[k] / n) for k in set(count_a) | set(count_b))
    if 1.0 - expected == 0.0:
        return None
    return (observed - expected) / (1.0 - expected)


def binarize(pairs: Sequence[Pair], label: str) -> list[Pair]:
    return [(IN if a == label else OUT, IN if b == label else OUT) for a, b in pairs]


def one_vs_rest_kappa(pairs: Sequence[Pair], label: str) -> float | None:
    """Kappa for one category against all others collapsed."""
    return cohen_kappa(binarize(pairs, label))


def category_counts(pairs: Sequence[Pair], label: str) -> dict[str, int]:
    """How many items each rater put in this category, plus the union and intersection.

    `n_either` is the support the interpretability floor is tested against: a category can be
    well agreed on and still rest on too few items to say anything about.
    """
    a_hits = [a == label for a, _ in pairs]
    b_hits = [b == label for _, b in pairs]
    return {
        "n_rater_a": sum(a_hits),
        "n_rater_b": sum(b_hits),
        "n_either": sum(1 for x, y in zip(a_hits, b_hits) if x or y),
        "n_both": sum(1 for x, y in zip(a_hits, b_hits) if x and y),
    }


def confusion_matrix(pairs: Sequence[Pair], labels: Sequence[str]) -> list[list[int]]:
    """Rows are rater A, columns rater B, in the order `labels` gives."""
    index = {label: i for i, label in enumerate(labels)}
    counts = [[0] * len(labels) for _ in labels]
    for a, b in pairs:
        counts[index[a]][index[b]] += 1
    return counts


def _resample(pairs: Sequence[Pair], clusters: Sequence[str], unit: str,
              rng: random.Random) -> list[Pair]:
    if unit == "item":
        return [pairs[rng.randrange(len(pairs))] for _ in range(len(pairs))]
    if unit == "conversation":
        grouped: dict[str, list[Pair]] = {}
        for pair, cluster in zip(pairs, clusters):
            grouped.setdefault(cluster, []).append(pair)
        keys = sorted(grouped)
        drawn: list[Pair] = []
        for _ in range(len(keys)):
            drawn.extend(grouped[keys[rng.randrange(len(keys))]])
        return drawn
    raise ValueError(f"unknown bootstrap unit {unit!r}")


def _percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolated percentile. q in [0, 1]."""
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = q * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def bootstrap_ci(pairs: Sequence[Pair], clusters: Sequence[str],
                 statistic: Callable[[Sequence[Pair]], float | None], *,
                 unit: str, resamples: int, seed: int, level: float,
                 max_undefined_fraction: float) -> dict:
    """Seeded percentile bootstrap interval for a statistic over label pairs.

    `unit` decides what gets resampled. "conversation" draws whole conversations with
    replacement, which is the right unit when several items share one conversation's context;
    "item" draws items, which treats them as independent and gives a narrower interval.

    Replicates whose statistic is undefined are excluded and counted. Above
    `max_undefined_fraction` the interval is marked not interpretable, because it then
    describes only the resamples in which the category happened to appear.
    """
    rng = random.Random(seed)
    values, undefined = [], 0
    for _ in range(resamples):
        value = statistic(_resample(pairs, clusters, unit, rng))
        if value is None:
            undefined += 1
        else:
            values.append(value)

    fraction = undefined / resamples if resamples else 1.0
    tail = (1.0 - level) / 2.0
    out = {
        "level": level,
        "unit": unit,
        "resamples": resamples,
        "seed": seed,
        "undefined_replicates": undefined,
        "undefined_fraction": fraction,
        "low": None,
        "high": None,
        "interpretable": False,
        "reason": None,
    }
    if not values:
        out["reason"] = "every resample gave an undefined statistic"
        return out
    out["low"] = _percentile(values, tail)
    out["high"] = _percentile(values, 1.0 - tail)
    if fraction > max_undefined_fraction:
        out["reason"] = (
            f"{undefined}/{resamples} resamples had an undefined statistic "
            f"(> {max_undefined_fraction:.0%}); the interval covers only the rest"
        )
        return out
    out["interpretable"] = True
    return out
