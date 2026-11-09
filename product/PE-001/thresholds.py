"""Pre-registered thresholds for PE-001.

Every value here names where it came from. Approved by Kapardhi on 2026-11-08, before any code
existed, as `docs/product/evals/PE-001-dataset-audit.md` records. Under CLAUDE.md rule 2 none of
them moves after a result has been seen; if one must, the change and its reason go in that
record's Change log.
"""

from __future__ import annotations

# --- Gate 1, condition 1 -------------------------------------------------------------------------
# A class with fewer than this many items cannot be measured, whatever a model does. The value and
# the handling (report the count, mark it not measurable, never drop or silently merge) follow the
# interpretability floor EXP-000 pre-registered for the same reason.
MIN_CLASS_N = 10

# --- Gate 1, condition 2 -------------------------------------------------------------------------
# Memory-dependent items needed for the corpus to be able to teach behaviour over time.
# PE-001's Hypothesis, condition 2.
MIN_MEMORY_DEPENDENT = 30

# How many items the context-stripped re-label sample holds, when the automatic lower bound falls
# short and condition 2 reads NOT_ESTABLISHED. PE-001's measurement D(2).
RECHECK_SAMPLE_N = 30

# --- Gate 1, conditions 3 and 4 ------------------------------------------------------------------
MAX_CROSS_SPLIT_DUPLICATES = 0
MAX_PILOT_OVERLAP = 0
REQUIRED_LABELER_COVERAGE = 1.0  # of items destined for dev or test

# --- Reporting only, never thresholded -----------------------------------------------------------
# Characters per token, for the estimated prompt length in measurement G. An estimate and labelled
# as one everywhere it appears: no Qwen tokenizer is loaded, because that would mean a download and
# this script runs on Kapardhi's machine with no network dependency. PE-002 replaces the estimate
# with a tokenizer count when it builds real prompts.
CHARS_PER_TOKEN_ESTIMATE = 4.0

# An `action` value longer than this, or a distinct-action count above this share of items, means
# the column probably holds free text rather than a closed class set. Class names are then withheld
# from the output and replaced by hashes, because free text in that column could carry client
# content. Claude Code's choice, 2026-11-08, defensive rather than pre-registered: it changes what
# is printed, never a threshold or a verdict.
MAX_CLASS_NAME_CHARS = 40
MAX_CLASS_NAME_WORDS = 6
MAX_DISTINCT_CLASSES = 50
MAX_CLASS_CARDINALITY_SHARE = 0.5


def meets_floor(n: int, floor: int = MIN_CLASS_N) -> bool:
    """True when a count meets a floor. Integer comparison, so no tolerance is needed here.

    EXP-000 and EXP-002 carry float tolerances because they compare kappa and rho against
    thresholds. PE-001's gate conditions are all counts, so an exact comparison is correct and a
    tolerance would be wrong.
    """
    return n >= floor
