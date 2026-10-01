# EXP-000: Label feasibility (abstention agreement)

Status: Planned
Owner: Kapardhi
Created: 2026-10-01
Decision informed: ADR-003 (keep, merge, or redefine abstention types)
Blocked by: D3 (data source and second annotator)

## Hypothesis
Two independent human annotators agree on NO-OP vs value vs ABSTAIN type at κ ≥ 0.6 per
abstention type. Refuted if any abstention type falls below 0.6.

## Setup
- 60–100 (field, turn) items from realistic sales conversations, enriched for corrections,
  hedges, and multi-speaker turns.
- Two annotators label independently, without discussion, using a written guideline.
- Labels: NO-OP / VALUE(v) / ABSTAIN:insufficient / ABSTAIN:ambiguous / ABSTAIN:conflicting /
  HEDGED (kept separate to learn how people treat hedges).

### What Claude Code may build
- Item sampler and annotation sheet generator (one row per field × turn, context shown)
- Agreement script: Cohen's κ per category, confusion matrix, list of disagreements
- Draft of the annotation guideline (human edits and approves it)

### What Claude Code must not do
- Pre-label items, suggest labels, or act as an annotator. Model judgment and human judgment
  must stay distinct.

## Baseline
Chance agreement (κ = 0).

## Metric
Cohen's κ per category. Working threshold κ ≥ 0.6 per abstention type.

## Leakage check
Items used here are pilot items and must not enter the eventual test split.

## Result
(pending)

## Interpretation
(pending)

## Decision
(pending, human)

## Note on solo annotation
If no second annotator exists, intra-annotator agreement (relabel after ≥1 week, blind to first
labels) is a weaker fallback and must be reported as intra-annotator, not inter-annotator.
