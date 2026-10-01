# ADR-003: Typed abstention, distinct from NO-OP

Status: Proposed
Date: 2026-10-01
Supersedes: none

## Decision
- NO-OP: no relevant evidence this turn. Not counted as abstention.
- ABSTAIN:insufficient / ABSTAIN:ambiguous / ABSTAIN:conflicting: evidence exists but the value is
  not determinable.

## Why
Most fields are not mentioned in most turns. If "not mentioned" counts as abstention, abstention
metrics are dominated by trivial cases. LongMemEval-style abstention ("info absent") is the easy case.

## Assumptions
Humans can reliably distinguish the three abstention types.

## Alternatives
- Binary abstain.
- Confidence threshold only, no explicit label.
- Value + confidence with no abstain token.

## Failure modes
- Low inter-annotator agreement.
- Types collapse in practice.
- Hedged values ("might stretch to 45") remain unresolved.

## Consequences
- Easier: selective-prediction metrics become meaningful.
- Harder: requires human labels.

## Evidence
None yet. EXP-000 decides this ADR.
