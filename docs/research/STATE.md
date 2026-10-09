# StateLM: Current Research State

Last updated: 2026-10-09 · D1, D2 and D4 decided; EXP-000 closed without a result

This file is the one-page snapshot every session reads first. Keep it under 60 lines.
Detail lives in the linked files, not here.

## Stage

| Stage | Status |
|---|---|
| 1. Problem, gap, contribution | Drafted; D1, D2 and D4 decided 2026-10-09 |
| 2. Define X and Y (model contract) | Not started |
| 3. Data model | Not started |
| 4. Benchmark design | Not started |
| 5. Baselines | Not started |
| 6+. Architecture, training, eval | Not started |

## Decisions pending (Kapardhi)

None. All four are resolved and were moved here on his instruction; the 2026-10-09 decisions are
transcribed verbatim in EXP-000's Change log.

- D1, 2026-10-09 — ≤4B primary, size curve at ~1B / ~4B / ~8B, as proposed.
- D2, 2026-10-09 — benchmark first, model second (ADR-001 → Accepted); the benchmark is built
  from constructed conversations, real chats are at most a validation slice.
- D4, 2026-10-09 — ADR-002 → Accepted; ADR-003 stays Proposed until label feasibility is
  measured on constructed data.
- D3, 2026-10-02 — conversations available; second annotator identified (Annotator B);
  inter-annotator design. **"Second annotator identified (Annotator B)" no longer holds**
  (Kapardhi, 2026-10-09): no human second annotator is available. Noted beside it rather than
  deleted, on his instruction.

## ADRs

| ID | Title | Status |
|---|---|---|
| ADR-001 | Interaction-scoped, benchmark-first claim | Accepted |
| ADR-002 | Temporal memory is a deterministic ledger | Accepted |
| ADR-003 | Typed abstention, distinct from NO-OP | Proposed |
| ADR-004 | Novelty levels by construction, not thresholds | Accepted |
| ADR-005 | Similarity as a calibrated continuous covariate | Accepted |

Nothing may be built on a Proposed ADR as if it were Accepted.

## Experiments

| ID | Title | Status | Blocked by |
|---|---|---|---|
| EXP-000 | Label feasibility (abstention agreement) | Closed (no result) | closed 2026-10-09 |
| EXP-001 | Headroom probe (frontier vs small) | Planned | EXP-000 |
| EXP-002 | Schema novelty audit on SGD / SGD-X | Done | nothing |
| EXP-003 | Label feasibility, constructed conversations | Draft | his review; 2nd annotator |

## Tooling

Genesis (Ayush's genesis-kit. - https://github.com/ayush488-glitch/genesis-kit) adoption
deferred to Stage 4, when spec-bound engineering begins (ledger Apply, benchmark
construction, eval harness). Adopt with `genesis adopt .` read-only first; existing
docs/research/ is ingested as evidence, not rewritten. HumanLayer not used.

## Where things live

All under `docs/research/`: `research-question.md` (question, definitions, hypotheses),
`literature.md` (prior work), `architecture.md`, `knowns-unknowns.md`, `adr/`, `experiments/`.
