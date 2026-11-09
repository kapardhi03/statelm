"""Pre-registered thresholds for PE-002.

Approved by Kapardhi on 2026-11-09 ("approved, write stage 1"), before any code existed, as
`docs/product/evals/PE-002-baseline-ladder.md` records. Under CLAUDE.md rule 2 none of them moves
after a result has been seen; a change and its reason go in that record's Change log.
"""

from __future__ import annotations

# --- Gate 2 --------------------------------------------------------------------------------------
# The smallest difference this track can honestly call a result. Not a round number: the plan's
# §3.2 power table detects +10 pp on a 200-item test split about four times in five, and +5 pp at
# no size this corpus can reach. It is therefore also the smallest headroom worth fine-tuning into.
MIN_EFFECT_PP = 10.0

# Significance for the one primary comparison per condition. Every other pairing is secondary and
# Holm-corrected, because seven rungs would otherwise be 21 tests at this alpha.
ALPHA = 0.05

# --- Intervals -----------------------------------------------------------------------------------
# The deciding interval is a cluster bootstrap by conversation: items are (message, turn) rows from
# a few dozen conversations and are not independent. A Wilson interval is reported beside it and is
# never the headline. PE-001 measures the mean cluster size this is correcting for.
BOOTSTRAP_RESAMPLES = 10_000
BOOTSTRAP_SEED = 0

# --- The split, pre-registered in the plan's §3.2 ------------------------------------------------
# 200 / 100 / remainder, assigned by conversation. The plan's rule is "by schema and domain", which
# is impossible on a one-deployment, one-schema corpus, so §3.2(iii) records that the assignment is
# by conversation and that the consequence is L0-only results — a scope statement after Q12, not a
# defect.
TEST_ITEMS_TARGET = 200
DEV_ITEMS_TARGET = 100
SPLIT_SEED = 0

# --- Stage 2 only, listed here so one file holds every pre-registered number ---------------------
FEWSHOT_K = 8          # B3. The example ids and their order go in the run config.
RUNS_PER_RUNG = 3      # Providers are not deterministic even at temperature 0.
TEMPERATURE = 0.0
