"""Pre-registered thresholds for EXP-002.

Every number in this module is fixed in
`docs/research/experiments/EXP-002-schema-novelty-audit.md` BEFORE any run. Changing one
requires a Change log entry in that file, written by the researcher. Nothing here may be
altered after seeing a result.
"""

from __future__ import annotations

# Step 1 gate, on (service, slot) instances with raw (N0) names.
GATE_SLOT_BAND: tuple[float, float] = (60.0, 70.0)
GATE_INTENT_BAND: tuple[float, float] = (66.0, 76.0)

# H1, Step 2.
COSINE_THRESHOLD: float = 0.8
JACCARD_THRESHOLD: float = 0.5
H1_MIN_RATE: float = 50.0

# H2, Step 3. Refutation rule set 2026-10-01, pre-run, prompted by SGD-X Table 1 and by no H2
# data. H2 holds only if both conditions hold under both embedding models.
#   (a) one-sided paired Wilcoxon signed-rank on per-slot cosine, v5 below v1
#   (b) Spearman rho between variant index and per-variant mean cosine
# The bound in (b) is exact, not approximate: with n = 5 a perfectly decreasing order gives
# rho = -1.0 and a single adjacent inversion gives rho = exactly -0.9, so an inclusive <= -0.9
# admits one adjacent inversion and no more.
H2_WILCOXON_ALPHA: float = 0.01
H2_SPEARMAN_MAX: float = -0.9

#: Floating-point slack for condition (b) only. See `spearman_meets_bound`.
H2_SPEARMAN_TOLERANCE: float = 1e-9

# Retired 2026-10-01, before ever being used: the previous H2 selected L1 material by
# measurement, which ADR-004 forbids. Kept here as a note, not as live thresholds.
#   H2_C1_MAX_EXACT_RATE = 70.0
#   H2_C2_MIN_RETAINED   = 80.0

EMBEDDING_INPUT_TEMPLATE: str = "{name}: {description}"

#: Pre-registered embedding models. Revisions are resolved and recorded per run.
EMBEDDING_MODELS: tuple[str, ...] = (
    "sentence-transformers/all-MiniLM-L6-v2",
    "BAAI/bge-base-en-v1.5",
)

#: SGD-X variant indices, in the order the paper defines (v1 closest to the original).
VARIANTS: tuple[int, ...] = (1, 2, 3, 4, 5)


def in_band(value: float, band: tuple[float, float]) -> bool:
    """Inclusive at both ends: a rate sitting exactly on a band edge passes."""
    low, high = band
    return low <= value <= high


def spearman_meets_bound(rho: float) -> bool:
    """H2 condition (b), with the boundary behaving as the rule intends.

    The rule is "Spearman rho <= -0.9, which allows at most one adjacent inversion". With n = 5
    those two statements agree in exact arithmetic: a single adjacent inversion gives
    sum(d^2) = 38 and rho = 1 - 6*38/120 = -0.9 precisely. In floating point that same case
    computes as -0.8999999999999998, which is 2.2e-16 ABOVE the bound, so a bare `rho <= -0.9`
    would reject the one case the rule explicitly admits.

    The tolerance is therefore applied to honour the rule, not to loosen it. It is nine orders of
    magnitude smaller than the gap to the next admissible configuration: two adjacent inversions
    give rho = -0.8, which this still rejects by a margin of 0.1.
    """
    return rho <= H2_SPEARMAN_MAX + H2_SPEARMAN_TOLERANCE
