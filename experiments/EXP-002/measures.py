"""Statistical measures for H1 and H2.

Each function here feeds a verdict, so each is covered by `tests/test_measures.py`. The
one-sided test in particular is easy to orient backwards, which is why its direction is
asserted against synthetic data rather than assumed.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats


def strictly_decreasing(values: Sequence[float]) -> bool:
    """True if every step goes down. Reported for H2, no longer the deciding rule."""
    vals = list(values)
    return all(b < a for a, b in zip(vals, vals[1:]))


def spearman_against_index(means: Sequence[float]) -> tuple[float, float]:
    """Spearman rho and p-value between position (1..n) and the given means.

    With n = 5, a perfectly decreasing order gives rho = -1.0 and one adjacent inversion gives
    rho = exactly -0.9, which is what makes H2's inclusive <= -0.9 bound admit exactly one
    inversion.
    """
    vals = list(means)
    if len(vals) < 3:
        raise ValueError("Spearman needs at least 3 points")
    index = list(range(1, len(vals) + 1))
    result = stats.spearmanr(index, vals)
    return float(result.statistic), float(result.pvalue)


def wilcoxon_lower(x: Sequence[float], y: Sequence[float]) -> tuple[float, float]:
    """One-sided paired Wilcoxon signed-rank test of "x is lower than y".

    Used for H2 condition (a) with x = v5 cosines and y = v1 cosines. Returns (statistic,
    p-value). If no pair differs, there is no evidence of a shift, so the p-value is 1.0 and
    the statistic 0.0; scipy raises on that input instead.
    """
    a, b = np.asarray(x, dtype=np.float64), np.asarray(y, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"wilcoxon_lower needs paired input, got {a.shape} and {b.shape}")
    if a.size == 0:
        raise ValueError("cannot test an empty sample")
    if not np.any(a != b):
        return 0.0, 1.0
    result = stats.wilcoxon(a, b, alternative="less")
    return float(result.statistic), float(result.pvalue)


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float:
    """Cohen's kappa for two binary labellings of the same items.

    Returns 1.0 when both labellings are identical and constant, where chance agreement is
    already 1.0 and kappa is otherwise undefined; 0.0 when they are constant but different.
    """
    la, lb = [bool(v) for v in a], [bool(v) for v in b]
    if len(la) != len(lb):
        raise ValueError(f"kappa needs equal lengths, got {len(la)} and {len(lb)}")
    if not la:
        raise ValueError("cannot compute kappa over an empty sample")
    n = len(la)
    observed = sum(x == y for x, y in zip(la, lb)) / n
    pa, pb = sum(la) / n, sum(lb) / n
    expected = pa * pb + (1 - pa) * (1 - pb)
    if expected == 1.0:
        return 1.0 if observed == 1.0 else 0.0
    return (observed - expected) / (1 - expected)
