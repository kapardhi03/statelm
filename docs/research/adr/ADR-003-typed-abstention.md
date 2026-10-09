# ADR-003: Typed abstention, distinct from NO-OP

Status: Proposed
Date: 2026-10-01
Supersedes: none

## Decision
- NO-OP: no relevant evidence this turn. Not counted as abstention.
- ABSTAIN:insufficient / ABSTAIN:ambiguous / ABSTAIN:conflicting: evidence exists but the value is
  not determinable.

**Status unchanged: still Proposed, on Kapardhi's instruction, 2026-10-09 (D4).** Transcribed
from Kapardhi, 2026-10-09, verbatim: "D4: change ADR-002's status to Accepted. ADR-003 stays
Proposed until label feasibility is measured on constructed data." EXP-000, which was to supply
that measurement, is closed without a result on the same instruction; label feasibility moves to
constructed conversations (EXP-003, draft).
*Flagged by Claude Code, not part of his instruction:* the Evidence section below still reads
"EXP-000 decides this ADR", which no longer holds now that EXP-000 is closed with no valid run.
Left as written, because an ADR's text is Kapardhi's.

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
