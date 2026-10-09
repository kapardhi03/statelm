# ADR-002: Temporal memory is a deterministic ledger outside the model

Status: Accepted
Date: 2026-10-01
Supersedes: none
Status changed on Kapardhi's instruction, 2026-10-09 (was Proposed).

## Decision
The model emits only turn-level operations. Current state and field history are computed by a
deterministic `Apply(Z_{t-1}, ops)` over an append-only, versioned ledger. The model never outputs
full state or history.

**Accepted on Kapardhi's instruction, 2026-10-09, resolving the ledger half of D4.**
Transcribed from Kapardhi, 2026-10-09, verbatim: "D4: change ADR-002's status to Accepted.
ADR-003 stays Proposed until label feasibility is measured on constructed data." The Decision
paragraph above is unchanged; no assumption, failure mode or consequence below was tested by
this acceptance.

## Why
- Keeps model output and derived state distinct.
- MemOps: ordered trajectory reconstruction is the weakest capability even for strong models, so
  the model should not be asked to do it.
- MemOps: the parametric memory baseline performed poorly across almost all metrics.

## Assumptions
- All relevant temporal behavior is expressible as ops on schema fields.
- Z_{t-1} plus dialogue history is sufficient context for the next ops.

## Alternatives
- Regenerate full state every turn.
- Model generates history directly.
- Learned memory module or vector store.

## Failure modes
- Error compounding: one wrong op persists until explicitly repaired.
- Exposure bias: trained on gold prior state, deployed on its own predictions.
- Fields that don't fit ops (multi-valued, conditional).

## Consequences
- Easier: exact, free history queries; op errors separable from state errors.
- Harder: repair requires explicit RETRACT / UPDATE.

## Evidence
SOM-DST precedent (state as overwritable memory). MemOps trajectory findings.
To test: gold vs predicted prior-state gap.
