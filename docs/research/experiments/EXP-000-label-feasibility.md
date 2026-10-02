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
  (sample_items.py), run locally by Kapardhi
- Agreement script: Cohen's κ per category, confusion matrix, list of disagreements
- Draft of the annotation guideline (human edits and approves it)
- PII scrubber (scrub.py), run locally by Kapardhi
- Conversation extractor (extract.py), run locally by Kapardhi

### What Claude Code must not do
- Pre-label items, suggest labels, or act as an annotator. Model judgment and human judgment
  must stay distinct.

## Baseline
Chance agreement (κ = 0).

## Metric
Cohen's κ per category. Working threshold κ ≥ 0.6 per abstention type.

## Pre-registered measurement choices
Decided by Kapardhi, 2026-10-02, before any sheet was labelled. Implemented in
`experiments/EXP-000/thresholds.py`, which names the provenance of each value. Nothing here may
change after a real run has been seen; if one must, the change and its reason are recorded below.

| | Choice | Why it was a choice at all |
|---|---|---|
| Interpretability floor | A category with fewer than 10 items (`n_either`, the count of items *either* rater put in it) is reported with all its counts and marked **not interpretable**, never dropped or hidden. The hypothesis reads *cannot be evaluated* rather than passing when an abstention type falls below it. | Three agreed items give κ = 1.000, which would otherwise look like the strongest result in the table. |
| Bootstrap unit | Primary: **conversation** (cluster bootstrap). Secondary: item, reported but never the headline. | Five fields times one turn means five items sharing one conversation's context, so items are not independent and an item-level interval is too narrow. |
| Undefined replicates | Excluded from the percentile interval and counted. Above 5% undefined the interval itself is marked not interpretable. | A replicate in which the category does not appear has no defined κ. Scoring it 0 would bias the interval downward; dropping it silently would describe only the resamples where the category happened to appear. |
| Value agreement | **strict** normalization (case, whitespace, trailing punctuation) is the primary figure. A **number-aware** figure, which resolves magnitude words so "40-45 lakhs", "40 to 45 lakhs" and "40–45 L" are equal, is reported separately and never replaces it. | Strict is a lower bound that cannot flatter the annotators. The gap between the two says how much value disagreement is formatting. Hedge words are deliberately *not* collapsed, since HEDGED is a label of its own. |
| HEDGED | **Rule (a):** HEDGED records the tentative value in the value column ("might stretch to 45" -> label HEDGED, value 45). | `research-question.md` lists hedged statements as Unresolved. This fixes an operational rule so annotation can proceed; it does not resolve the question, and the note there says so. |
| Threshold comparison | κ ≥ 0.6 with a 1e-9 tolerance. | A one-vs-rest table of (2, 1, 1, 14) has an exact κ of 3/5 but computes as 0.5999999999999996, so a bare comparison would report BELOW on a category that exactly meets the threshold. n = 18 is an ordinary size for a rare abstention type here. Added 2026-10-02, before any real run; a test pins the table and fails if the hazard ever disappears. |

ADR-003 was **Proposed** when these were pre-registered, and D4 is pending. EXP-000 is the
experiment that tests ADR-003, so every choice above is provisional on a taxonomy that may change.

### Change log
- 2026-10-02: measurement choices above pre-registered by Kapardhi. No sheets labelled yet.

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
