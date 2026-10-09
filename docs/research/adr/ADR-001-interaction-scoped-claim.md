# ADR-001: Interaction-scoped, benchmark-first research claim

Status: Accepted
Date: 2026-10-01
Supersedes: none
Status changed on Kapardhi's instruction, 2026-10-09 (was Proposed).

## Decision
The research claim is the performance and calibration of schema-conditioned state-delta tracking
under controlled schema novelty, with temporal revision and typed abstention, across model sizes.
The benchmark is the primary expected contribution; the model is secondary.

**Accepted on Kapardhi's instruction, 2026-10-09, resolving D2.** Transcribed from Kapardhi,
2026-10-09, verbatim: "D2: benchmark first, model second. Change ADR-001's status to Accepted.
The benchmark is built from constructed conversations; real chats are at most a validation
slice." The last sentence is his and is recorded here as given; the Decision paragraph above is
unchanged.

## Why
Each capability alone is covered in prior work (`docs/research/literature.md`). Only their
interaction (H-A, H-B, H-C) is open.

## Assumptions
- Interaction effects exist and are measurable.
- Frontier models do not saturate the task.

## Alternatives
- Model-first "best small CRM state model": engineering, not research.
- MemOps-style schema-free memory benchmark: already done.
- Pure SGD-X DST: mature line of work.

## Failure modes
- No interaction found: difficulty is additive.
- Frontier saturates the task.
- Benchmark too synthetic to matter.

## Consequences
- Easier: defensibility; negative results still publishable.
- Harder: needs human-labeled test data; slower path to a usable model.

## Evidence
SGD-X schema sensitivity and MemOps trajectory fragility motivate it. No direct evidence of
interaction yet (EXP-001).
