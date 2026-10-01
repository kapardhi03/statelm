# EXP-001: Headroom probe

Status: Planned
Owner: Kapardhi
Created: 2026-10-01
Decision informed: ADR-001 branch (benchmark-led vs model-led vs pivot)
Blocked by: EXP-000 (abstention labels must be defined first)

## Hypothesis
A frontier model is clearly imperfect at novelty levels L2+ and on typed abstention, and a
zero-shot ~3–4B model is clearly worse than the frontier model.

## Setup
- Pilot of 30–50 conversations across L0–L4.
- Mix: SGD-X-derived items (cheap schema novelty, see EXP-002) and hand-written sales
  conversations containing revisions and ambiguity.
- Models: one frontier model; one ~3–4B instruct model with schema prompting.
- Same prompt template for both; prompt frozen before seeing pilot results.

## Baseline
Frontier vs small zero-shot.

## Metric
By novelty level: value accuracy, stale-value rate, abstention precision / recall.

## Leakage check
Pilot conversations are never reused in train or final test. Prompt iteration happens on a
separate dev slice, never on the pilot.

## Result
(pending)

## Interpretation
(pending) A pilot this small is a go/no-go signal, not evidence for any claim.

## Decision
(pending, human)
