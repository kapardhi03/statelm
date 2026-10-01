# StateLM: Current Research State

Last updated: 2026-10-01 · Stage 1 (problem definition) complete, awaiting decisions

This file is the one-page snapshot every session reads first. Keep it under 60 lines.
Detail lives in the linked files, not here.

## Stage

| Stage | Status |
|---|---|
| 1. Problem, gap, contribution | Drafted, awaiting 4 decisions below |
| 2. Define X and Y (model contract) | Not started |
| 3. Data model | Not started |
| 4. Benchmark design | Not started |
| 5. Baselines | Not started |
| 6+. Architecture, training, eval | Not started |

## Decisions pending (Kapardhi)

- D1. "Small" bound: proposed ≤4B primary, size curve at ~1B / ~4B / ~8B
- D2. Contribution ordering: proposed benchmark-first, model-second (ADR-001)
- D3. Real data source and second annotator for EXP-000
- D4. Accept / modify / reject ADR-002 (ledger) and ADR-003 (typed abstention)

## ADRs

| ID | Title | Status |
|---|---|---|
| ADR-001 | Interaction-scoped, benchmark-first claim | Proposed |
| ADR-002 | Temporal memory is a deterministic ledger | Proposed |
| ADR-003 | Typed abstention, distinct from NO-OP | Proposed |
| ADR-004 | Novelty levels by construction, not thresholds | Accepted |

Nothing may be built on a Proposed ADR as if it were Accepted.

## Experiments

| ID | Title | Status | Blocked by |
|---|---|---|---|
| EXP-000 | Label feasibility (abstention agreement) | Planned | D3 |
| EXP-001 | Headroom probe (frontier vs small) | Planned | EXP-000 |
| EXP-002 | Schema novelty audit on SGD / SGD-X | Done (awaiting decision) | nothing |

## Where things live

- Research question, definitions, hypotheses: `docs/research/research-question.md`
- Prior work and what it means for us: `docs/research/literature.md`
- Current agreed architecture (Mermaid): `docs/research/architecture.md`
- Knowns, unknowns, risks, research clusters: `docs/research/knowns-unknowns.md`
- ADRs: `docs/research/adr/`
- Experiment records: `docs/research/experiments/`
