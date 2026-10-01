# EXP-002: Schema novelty audit on SGD / SGD-X

Status: Planned
Owner: Kapardhi
Created: 2026-10-01
Revised: 2026-10-01 (pre-run, see Change log)
Decision informed:
- H1: whether SGD can supply L2 (new-field) items, or we must construct our own.
- H2: whether SGD-X is valid L1 material.
Blocked by: nothing

## Change log

- **2026-10-01, before any run and before any code existed.** Hypothesis, Metric and
  "Decision informed" revised by Kapardhi. The original hypothesis ("refuted if fewer than ~20%
  of unseen-service slots have a near match at cosine >= 0.8") was unfalsifiable once the
  sanity-check gate passed: exact name matches are a subset of the cosine >= 0.8 set, so a gate
  asserting ~65% exact matches over the same population makes a <20% result arithmetically
  impossible. Replaced by H1 and H2, which are evaluated on populations the gate does not already
  determine. At the time of this change no run had been executed, no metric had been computed,
  and `experiments/EXP-002/` did not exist.
- **2026-10-01, same revision.** Step 4 (proposed L0 / L1 / L2 bin assignment) dropped entirely.
  This experiment emits no novelty-level labels. Similarity is reported as a per-item covariate
  only. Rationale recorded in ADR-004 (Proposed), which cites this experiment as evidence.

## Hypothesis

**Gate (pre-condition, not a hypothesis).** The SGD-X exact-name overlap figures reproduce inside
the bands in Metric below. If they do not, the experiment stops and reports. H1 and H2 are not
evaluated and no similarity work is done.

**H1 (semantic near-duplication beyond exact matches).** Among slots in unseen test services that
have **no exact name match** in train, a majority (>= 50%) have a nearest train slot at
cosine >= 0.8 under **both** embedding models. Refuted if < 50%.

**H2 (SGD-X novelty is surface-level).** For SGD-X v1-v5 compared against **original** train, the
exact-name match rate drops by >= 30 points relative to the original schemas, while >= 80% of
variant slots keep cosine >= 0.8 to their own original slot under both models. Refuted if either
condition fails.

## Setup

### Data and provenance
- Source: `google-research-datasets/dstc8-schema-guided-dialogue`, pinned to one commit SHA,
  cloned to `data/raw/sgd/<commit-sha>/` (gitignored). SHA-256 of every schema file read is
  recorded in the run config.
- Files read: `train/schema.json`, `test/schema.json`, and `sgd_x/data/v1..v5/*/schema.json`.
  No dialogue files, no state annotations, no labels of any kind are read.
- No split is created, so this experiment writes no entry in `data/splits/schema_assignment.json`.

### Populations
- **Train** = `train/schema.json` only. Dev is not used.
- **Unseen service** = a `service_name` in `test/schema.json` that is not present in
  `train/schema.json`.
- **Primary unit** = `(service, slot)` instances. A slot name occurring in three unseen services
  counts three times.
- **Secondary unit** = unique names. Reported, never gating.
- All slots are in scope: categorical and non-categorical, required and optional.
- Intent names are a second sanity point (see Metric). Intent parameters are out of scope.

### Name normalization pipelines
- **N0** = raw string, exactly as it appears in the schema. The gate and both hypotheses use N0.
- **N1** = lowercase + split `snake_case` and `camelCase` into tokens.
- **N2** = N1 + singularize + drop stopwords.
- No abbreviation expansion in any pipeline. N1 and N2 are reported as secondary only.

### Measures computed per unseen-service slot, against all train `(service, slot)` instances
1. Exact normalized-name match, under N0 (primary) and N1, N2 (secondary).
2. Token Jaccard on N1 tokens of **names only**, with the nearest train slot and its score.
3. Embedding cosine to the nearest train slot, computed twice, once per model, reported side by
   side. Neither model is treated as the answer.

### Embedding configuration
- Models: `sentence-transformers/all-MiniLM-L6-v2` and `BAAI/bge-base-en-v1.5`. Both run locally.
  Revisions pinned at acquisition and recorded in the run config.
- Input template: `"{name}: {description}"`, raw name, no service name or service description.
  Its SHA-256 is recorded in the run config under `input_template_hash`.
- Pooling and any required instruction prefix follow each model card. Vectors are L2-normalized.

### SGD-X comparison direction
- Variant test slots are compared against **original** train slots, matching the SGD-X protocol
  (train on SGD, test on variants).
- For H2 additionally: each variant slot against its own original slot, a 1:1 mapping by
  `(service_name, slot_name index)`.

### Code and outputs
- Entry points: `experiments/EXP-002/run_sanity_check.py` (gate) and
  `experiments/EXP-002/run_audit.py` (H1, H2). Local `pyproject.toml`, `uv`-managed.
- Run id format: `YYYYMMDDTHHMMSSZ-<git-short-sha>`.
- `runs/EXP-002/<run-id>/` holds `config.json`, `metrics.json`, `sanity_check.json`,
  `per_slot.jsonl` (tracked), `log.txt`.
- `config.json` records: git commit, run id, seed, dataset repo URL and pinned commit SHA, SHA-256
  per schema file, normalization pipeline ids and version, both embedding model names and
  revisions, `input_template_hash`, and every threshold in Metric below.
- The ">= 3 seeds" convention does not apply: nothing is trained or sampled and the pipeline is
  deterministic given pinned model revisions. The robustness axes are 2 embedding models x 5
  SGD-X variants. A seed is still recorded.

## Baseline

SGD's official seen / unseen service label, operationalized as the service-name membership test
above. The comparison tells us whether that label, as published, separates novel schema material
from material that is lexically or semantically already present in train.

## Metric

All thresholds below are fixed before any run. The gate is evaluated first and alone.

### Gate (sanity check, N0, primary unit)
Reproduce the SGD-X figures: of names in test schemas for services unseen in train, 71% of intent
names and 65% of slot names exactly match train names.
- **Passes** if slot exact-match rate falls in **60-70%** AND intent exact-match rate falls in
  **66-76%**, both on the primary unit.
- Otherwise the experiment **stops and reports**. No Jaccard, no embeddings, no H1, no H2.
- Reported alongside, not gating: the same two rates on unique names, and under N1 and N2.

### H1
- Population: unseen-service slots with no N0 exact name match in train (the complement of the
  gate's matched set). The N1-based population is reported as secondary.
- Primary metric: % of that population whose nearest train slot has cosine >= 0.8 under both
  models. Supported if >= 50%, refuted if < 50%.
- Reported alongside: the per-model rates, the full nearest-neighbor cosine distribution, and the
  % clearing Jaccard >= 0.5.

### H2
- Exact-name match rate of variant test slots against original train slots, N0, primary unit,
  same unseen-service population as the gate. Condition 1 holds if this rate is at least 30
  points below the gate's slot exact-match rate.
- Condition 2 holds if >= 80% of variant slots keep cosine >= 0.8 to their own original slot under
  both models.
- H2 is supported only if both conditions hold. Refuted if either fails.
- Reported alongside: per-variant distributions, not only means.

### Embedding-model agreement (reported for H1 and H2, not gating)
- Primary: top-1 identity agreement rate, the share of slots where both models pick the same
  nearest train slot.
- Secondary: Cohen's kappa on the binary cosine >= 0.8 decision.

### Not emitted
No L0 / L1 / L2 / L4 assignment, and no novelty-level label of any kind, appears in
`metrics.json`, `per_slot.jsonl`, or the Result section. Similarity is a covariate (ADR-004,
Proposed).

## Open items (must be fixed before the run, pre-registration material)

These are population and aggregation definitions that H1 and H2 do not pin down. Written here
rather than chosen in code.

- **O1.** H2 aggregation: must each of v1-v5 satisfy both conditions individually (strict
  reading, currently assumed), or is the mean across the five variants the test?
- **O2.** H2 condition 2 population: all slots in the variant schemas, only slots of test
  services, or only slots of unseen test services?
- **O3.** H1 "nearest train slot ... under both models": each model's own nearest neighbor must
  clear 0.8 (currently assumed, and consistent with top-1 identity agreement being a separate
  metric), or must both models agree on the same nearest train slot and that slot clear 0.8?
- **O4.** Nearest-neighbor search space: all train `(service, slot)` instances, which is what
  "name + description" embeddings imply since the same name carries different descriptions in
  different services (currently assumed), or unique names with one description picked per name?

## Leakage check

Not applicable in the training sense: schemas only, no labels, no model trained or prompted.
`test/schema.json` is read, which is schema material and not a label; no dialogue state
annotations are read at any point. StateLM's own `data/splits/test/` is untouched and uncreated.

## Result
(pending)

## Interpretation
(pending)

Required caveat, must appear in the filled Interpretation: "novel relative to SGD-train" must
never be reported as "unseen by the model". This experiment measures overlap between SGD train
schemas and SGD test schemas. It says nothing about whether a pretrained model has already seen
SGD, which remains an open contamination risk in `docs/research/knowns-unknowns.md`.

## Decision
(pending, human)
