# ADR-004: Novelty levels are assigned by construction, not by similarity thresholds

Status: Proposed
Date: 2026-10-01
Supersedes: none

## Decision
A benchmark item's novelty level is assigned by **how the item was constructed**, recorded as
provenance at construction time:

- paraphrase of a schema present in train -> L1
- field held out of train -> L2
- domain held out of train -> L4

Lexical overlap and embedding similarity to the nearest train field are **reported per item as a
covariate**, never used to assign or reassign a level. No experiment emits a novelty level derived
from a threshold.

This ADR does not change ADR-001, ADR-002 or ADR-003, and does not alter the ladder in
`docs/research/research-question.md`. It states how the ladder's levels are operationalized.

## Why
- The ladder's levels are statements about provenance ("surface only: renamed or redescribed",
  "new field, seen domain", "new domain"). A cosine threshold is not a statement about provenance.
- If thresholds assign levels, the novelty axis underneath the project's main claim becomes an
  artifact of whichever embedding models were chosen. The claim
  `Q_small(n) >= Q_frontier(n) - delta` would be indexed by a measurement rather than by a
  property of the data.
- Circularity: EXP-002's thresholds would define L1 and L2, and EXP-001 would then inherit that
  proxy as its independent variable.
- SGD-X shows a published seen / unseen label can be leaky (65% of slot names and 71% of intent
  names in unseen-service test schemas exactly match train names). The lesson taken here is that
  a level must come from a controlled construction operation and overlap must be measured and
  reported per item, which `research-question.md` already requires.

## Assumptions
- Every benchmark item's construction history is recorded and auditable at construction time.
- One construction operation dominates an item's novelty. Items built by more than one operation
  need an explicit rule (highest applicable level, or exclusion) that this ADR does not set.
- L3 (new value semantics) and L5 (seen fields in unseen combinations) have **no construction
  operation defined yet**. This ADR covers L1, L2 and L4 only, and leaves L3 and L5 open.
- Paraphrase strength is controllable, so that L1 is a level rather than a range.

## Alternatives
- **Threshold-assigned levels.** Cheap, needs no provenance metadata, and lets public datasets be
  binned directly. Rejected for the reasons above.
- **Official dataset seen / unseen labels.** Free, comparable to prior work, and leaky, which is
  exactly what EXP-002 measures.
- **Human-judged novelty ratings.** Closest to the construct, expensive, and needs its own
  agreement study before it can be used.
- **Hybrid: construction assigns, thresholds audit.** Provenance assigns the level; similarity is
  used only to flag items whose measured overlap contradicts their construction label. This is the
  nearest alternative to the decision above and differs from it only in whether a contradicting
  covariate can trigger exclusion.

## Failure modes
- A held-out field can be a near-duplicate in wording of a train field, so a construction label
  of L2 can overstate novelty. Mitigation is the reported covariate, and a dropped-item rule the
  hybrid alternative would add.
- Pretraining contamination is invisible to both schemes. An L4 domain held out of *our* train
  split may be fully familiar to the model. Construction-based levels say nothing about this.
- Provenance can rot: items edited after construction keep a stale level unless provenance is
  re-derived.
- A paraphrase generator with a narrow style makes L1 uniformly easy or uniformly hard, and the
  level hides that.

## Consequences
- Easier: levels are stable under a change of embedding model; EXP-001's independent variable is
  not defined by a measurement; similarity becomes an analysis variable that can disagree with the
  level, which is informative rather than contradictory.
- Harder: every item needs provenance metadata in the data model (Stage 3), and public-dataset
  items can only be used where their construction is known. SGD-X variants are paraphrases of SGD
  schemas, so they are candidate L1 material. A test-only SGD service is **not** automatically L2,
  because we did not hold that field out; EXP-002 measures how far such items are from train.

## Evidence
- EXP-002 (pending): exact-name overlap, Jaccard, and two-model embedding similarity for slots in
  unseen SGD test services, plus the same for SGD-X v1-v5 against original train.
- `docs/research/literature.md`: SGD-X (Lee et al. 2022) 12-18% JGA loss from rewording alone,
  65% slot-name and 71% intent-name exact overlap in unseen-service test schemas;
  Coca et al. 2023 on synthetic schema paraphrases as an L1-style augmentation.
- No evidence yet on L3 and L5 construction operations, or on paraphrase-strength control.
