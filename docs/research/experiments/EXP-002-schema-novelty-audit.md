# EXP-002: Schema novelty audit on SGD / SGD-X

Status: Planned
Owner: Kapardhi
Created: 2026-10-01
Decision informed: how novelty levels L0–L2 are operationalized; whether SGD-derived items can
serve as L1/L2 material in EXP-001
Blocked by: nothing

## Hypothesis
A large share of SGD test slots labelled "unseen" are lexical or semantic near-duplicates of
training slots, so the official seen/unseen label does not measure schema novelty. Refuted if
fewer than ~20% of unseen-service slots have a near match (embedding cosine ≥ 0.8) in train.

## Setup
- Source: `google-research-datasets/dstc8-schema-guided-dialogue` (SGD + SGD-X v1–v5 schemas).
- For every slot in test-only services, compute against all train slots:
  1. exact normalized-name match
  2. token Jaccard on names
  3. embedding cosine of `name + description` to nearest train slot, with TWO embedding models
     (the choice of model is itself an assumption; report both)
- Repeat for SGD-X variants to see how paraphrase shifts the distances.
- Sanity check: reproduce the SGD-X paper's slot-name overlap figure (~65%) before anything else.
  If it does not reproduce, stop and report.

## Baseline
SGD's official seen / unseen service label.

## Metric
- % of unseen-service slots with exact match / Jaccard ≥ 0.5 / cosine ≥ 0.8
- Agreement between the two embedding models on nearest-neighbor assignment
- Proposed bin assignment (L0 / L1 / L2) under stated thresholds, with counts

## Leakage check
Not applicable (analysis of schemas only, no labels used).

## Result
(pending)

## Interpretation
(pending)

## Decision
(pending, human)
