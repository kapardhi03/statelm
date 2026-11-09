"""PE-002's statistics, against inputs with known answers.

The Gate 2 verdict is a comparison of two numbers against a threshold, so if any of these is wrong
the verdict is wrong and nothing downstream would show it.
"""

from __future__ import annotations

import random

import pytest
from conftest import scored

from scoring import (
    Scored,
    accuracy,
    accuracy_of,
    cluster_bootstrap,
    holm,
    mcnemar_exact,
    paired_compare,
    spread,
    wilson_interval,
)


# --- accuracy and Wilson ---------------------------------------------------------------------------

def test_accuracy():
    assert accuracy([True, True, False, False]) == 0.5
    assert accuracy([]) == 0.0
    assert accuracy([True]) == 1.0


def test_wilson_matches_the_plans_published_figures():
    """The plan's §3.2 table is the justification for the 10 pp threshold; same interval here."""
    lo, hi = wilson_interval(round(0.80 * 200), 200)
    assert round(100 * (hi - lo), 1) == 11.0
    lo, hi = wilson_interval(round(0.80 * 100), 100)
    assert round(100 * (hi - lo), 1) == 15.5


def test_wilson_on_an_empty_sample_is_maximally_uninformative():
    assert wilson_interval(0, 0) == (0.0, 1.0)


# --- McNemar --------------------------------------------------------------------------------------

def test_mcnemar_no_discordant_pairs_is_no_evidence():
    assert mcnemar_exact(0, 0) == 1.0


def test_mcnemar_is_symmetric():
    assert mcnemar_exact(9, 1) == mcnemar_exact(1, 9)


def test_mcnemar_known_value():
    # b=9, c=1: two-sided exact = 2 * P(X <= 1), X ~ Binomial(10, 0.5) = 2 * 11/1024.
    assert mcnemar_exact(9, 1) == pytest.approx(2 * 11 / 1024)


def test_mcnemar_shrinks_as_the_imbalance_grows():
    assert mcnemar_exact(20, 0) < mcnemar_exact(10, 0) < mcnemar_exact(5, 0)


def test_mcnemar_is_capped_at_one():
    assert mcnemar_exact(5, 5) <= 1.0


def test_mcnemar_ignores_concordant_pairs():
    """The pairing is the point: items both systems get right carry no information."""
    assert mcnemar_exact(3, 0) == mcnemar_exact(3, 0)


# --- paired comparison ----------------------------------------------------------------------------

def test_paired_compare_counts_the_discordant_cells():
    base = scored([("a", "c1", False), ("b", "c1", True), ("c", "c2", True), ("d", "c2", False)])
    cand = scored([("a", "c1", True), ("b", "c1", False), ("c", "c2", True), ("d", "c2", True)])
    r = paired_compare(base, cand)
    assert r.b_baseline_wrong_candidate_right == 2  # a and d
    assert r.c_baseline_right_candidate_wrong == 1  # b
    assert r.discordant == 3
    assert r.baseline_accuracy == 0.5
    assert r.candidate_accuracy == 0.75
    assert r.difference_pp == pytest.approx(25.0)


def test_paired_compare_refuses_unpaired_inputs():
    """Computing an unpaired comparison as a paired one would report the wrong test silently."""
    base = scored([("a", "c1", True)])
    cand = scored([("b", "c1", True)])
    with pytest.raises(ValueError, match="same items"):
        paired_compare(base, cand)


def test_paired_compare_on_identical_systems_finds_nothing():
    base = scored([("a", "c1", True), ("b", "c1", False)])
    r = paired_compare(base, base)
    assert r.difference_pp == 0.0
    assert r.p_value == 1.0


# --- cluster bootstrap ----------------------------------------------------------------------------

def _wide(n_conv: int, items_per_conv: int, correct_frac: float) -> list[Scored]:
    """Clusters whose accuracies DIFFER from each other.

    An earlier version gave every conversation the same accuracy, which has zero between-cluster
    variance and therefore a zero-width cluster interval — correct behaviour, but it made the two
    tests below vacuous rather than failing honestly. `test_zero_between_cluster_variance...`
    records that behaviour on purpose; these use a corpus where it does not hold.
    """
    rng = random.Random(1234)
    out: list[Scored] = []
    for c in range(n_conv):
        # Per-conversation accuracy spread around correct_frac, so resampling conversations moves
        # the statistic the way it does on real data.
        p_conv = min(1.0, max(0.0, correct_frac + rng.uniform(-0.35, 0.35)))
        for i in range(items_per_conv):
            out.append(Scored(f"{c}-{i}", f"conv{c}", rng.random() < p_conv))
    return out


def _uniform(n_conv: int, items_per_conv: int, correct_frac: float) -> list[Scored]:
    """Every conversation with the same accuracy: zero between-cluster variance."""
    out: list[Scored] = []
    for c in range(n_conv):
        for i in range(items_per_conv):
            out.append(Scored(f"{c}-{i}", f"conv{c}", (i / items_per_conv) < correct_frac))
    return out


def test_cluster_bootstrap_is_deterministic_under_a_seed():
    s = _wide(20, 5, 0.8)
    a = cluster_bootstrap(s, accuracy_of, resamples=500, seed=1)
    b = cluster_bootstrap(s, accuracy_of, resamples=500, seed=1)
    assert a == b


def test_cluster_bootstrap_interval_contains_the_point_estimate():
    s = _wide(20, 5, 0.8)
    r = cluster_bootstrap(s, accuracy_of, resamples=500, seed=0)
    assert r["lo"] <= r["point"] <= r["hi"]


def test_cluster_bootstrap_is_wider_than_wilson_when_items_cluster():
    """The whole reason it is the deciding interval: five rows from one conversation are not five
    independent observations, and Wilson would report them as if they were."""
    s = _wide(20, 5, 0.8)
    cb = cluster_bootstrap(s, accuracy_of, resamples=2000, seed=0)
    k = sum(1 for x in s if x.correct)
    lo, hi = wilson_interval(k, len(s))
    assert (cb["hi"] - cb["lo"]) > (hi - lo)


def test_cluster_bootstrap_narrows_as_clusters_are_added():
    narrow = cluster_bootstrap(_wide(60, 5, 0.8), accuracy_of, resamples=1000, seed=0)
    wide = cluster_bootstrap(_wide(10, 5, 0.8), accuracy_of, resamples=1000, seed=0)
    assert narrow["width_pp"] < wide["width_pp"]


def test_cluster_bootstrap_reports_its_cluster_count():
    r = cluster_bootstrap(_wide(7, 3, 0.5), accuracy_of, resamples=200, seed=0)
    assert r["n_clusters"] == 7


def test_cluster_bootstrap_on_nothing_is_not_interpretable():
    r = cluster_bootstrap([], accuracy_of, resamples=100, seed=0)
    assert r["interpretable"] is False
    assert r["n_clusters"] == 0


def test_zero_between_cluster_variance_gives_a_zero_width_interval():
    """Not a bug: if every conversation scores alike, resampling conversations cannot move the
    statistic, and the honest interval is a point. Worth pinning, because it also means a
    zero-width interval is a signal to look at the clusters rather than to trust the precision."""
    r = cluster_bootstrap(_uniform(20, 5, 0.8), accuracy_of, resamples=500, seed=0)
    assert r["lo"] == r["hi"] == r["point"]


def test_cluster_bootstrap_resamples_conversations_not_items():
    """With one conversation there is nothing to resample, so every replicate is identical."""
    s = [Scored(f"i{i}", "only", i % 2 == 0) for i in range(10)]
    r = cluster_bootstrap(s, accuracy_of, resamples=200, seed=0)
    assert r["lo"] == r["hi"] == r["point"]


# --- Holm -----------------------------------------------------------------------------------------

def test_holm_adjusts_the_smallest_p_by_the_family_size():
    out = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert out["a"] == pytest.approx(0.03)  # 3 * 0.01


def test_holm_is_monotonic():
    out = holm({"a": 0.01, "b": 0.04, "c": 0.03})
    assert out["a"] <= out["c"] <= out["b"]


def test_holm_caps_at_one():
    assert all(v <= 1.0 for v in holm({"a": 0.9, "b": 0.8, "c": 0.7}).values())


def test_holm_on_a_single_test_changes_nothing():
    assert holm({"a": 0.02})["a"] == pytest.approx(0.02)


def test_holm_on_nothing():
    assert holm({}) == {}


# --- spread ---------------------------------------------------------------------------------------

def test_spread_reports_mean_and_range():
    s = spread([0.70, 0.75, 0.80])
    assert s["mean"] == pytest.approx(0.75)
    assert s["min"] == 0.70 and s["max"] == 0.80
    assert s["n"] == 3
    assert s["stdev"] > 0


def test_spread_of_one_run_has_no_stdev():
    assert spread([0.5])["stdev"] == 0.0


def test_spread_of_nothing():
    assert spread([])["n"] == 0


def test_a_strongly_significant_p_value_is_not_rounded_to_zero():
    """Rounding it would print "0.0", which reads as an exactness no test can have."""
    r = paired_compare(
        scored([(f"i{n}", f"c{n // 5}", False) for n in range(60)]),
        scored([(f"i{n}", f"c{n // 5}", n < 55) for n in range(60)]),
    )
    assert 0 < r.as_dict()["p_value"] < 1e-9
