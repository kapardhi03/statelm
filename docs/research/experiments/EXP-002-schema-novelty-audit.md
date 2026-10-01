# EXP-002: Schema novelty audit on SGD / SGD-X

Status: Running
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
  sanity-check gate passed: exact name matches are, with near certainty though not as a matter of
  arithmetic, also near matches under the cosine measure, so a gate asserting ~65% exact matches
  over the same population left no realistic path to a <20% result. (The qualifier matters: the
  embedding input carries each slot's description, so identical names do not strictly guarantee
  cosine >= 0.8. The original wording claimed arithmetic it did not have.) Replaced by H1 and H2, which are evaluated on populations the gate does not already
  determine. At the time of this change no run had been executed, no metric had been computed,
  and `experiments/EXP-002/` did not exist.
- **2026-10-01, same revision.** Step 4 (proposed L0 / L1 / L2 bin assignment) dropped entirely.
  This experiment emits no novelty-level labels. Similarity is reported as a per-item covariate
  only. Rationale recorded in ADR-004 (Proposed), which cites this experiment as evidence.
- **2026-10-01, same day, still pre-run.** H2 corrected by Kapardhi to align with ADR-004, where
  L1 means "paraphrase of a schema present in train". Its population moved from unseen-service
  slots to **seen-service** slots, and condition 1 became an absolute band (the exact-name match
  rate of variant names against original train falls to <= 70%, where the original test schemas
  match at 100%) in place of a ">= 30 point drop". The unseen-service version of both conditions
  is kept as secondary and decides nothing. The four open population and aggregation items were
  resolved by Kapardhi in the same message: O1, H2 is evaluated per variant with a separate
  verdict for each of v1-v5, no mean and no all-five requirement, and variants that pass are
  usable L1 material; O2, seen-service slots; O3, each model's own nearest neighbor must clear
  0.8; O4, the nearest-neighbor search space is all train `(service, slot)` instances. At the time
  of this change there was still no run, no computed metric, and no experiment code.

## Hypothesis

**Gate (pre-condition, not a hypothesis).** The SGD-X exact-name overlap figures reproduce inside
the bands in Metric below. If they do not, the experiment stops and reports. H1 and H2 are not
evaluated and no similarity work is done.

**H1 (semantic near-duplication beyond exact matches).** Among slots in unseen test services that
have **no exact name match** in train, a majority (>= 50%) have a nearest train slot at
cosine >= 0.8 under **both** embedding models. Refuted if < 50%.

**H2 (SGD-X novelty is surface-level), evaluated separately for each of v1-v5.** For SGD-X variant
slots of **seen** services compared against **original** train, the exact-name match rate falls to
<= 70%, where the original test schemas match at 100%, while >= 80% of variant slots keep
cosine >= 0.8 to their own original slot under both models. A variant is refuted if either
condition fails. Variants that pass both are usable L1 material.

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
  `train/schema.json`. **Seen service** = present in both.
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

### Measures computed per slot, against all train `(service, slot)` instances
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

### SGD-X comparison direction and population
- H2 population: slots of **seen** services in the variant test schemas, matching ADR-004's L1,
  a paraphrase of a schema that is present in train.
- Variant slot names are compared against **original** train slot names, matching the SGD-X
  protocol (train on SGD, test on variants).
- Condition 2 additionally pairs each variant slot with its own original slot, a 1:1 mapping by
  `(service_name, position in that service's slot list)`.
- The same two conditions are computed on unseen-service slots and reported as secondary. They
  decide nothing.
- Validation before H2 is computed, failing loudly rather than mismatching silently: each variant
  must carry the same service names, the same slot count per service, and the same slot order as
  the original schemas. If any differs, the 1:1 mapping is invalid and the run stops.
- The 100% exact-match baseline for original seen-service slots is computed, not assumed. If it
  is not 100%, that is reported as a finding about the schema files rather than absorbed silently.

### Code and outputs
- Entry points: `experiments/EXP-002/run_sanity_check.py` (gate) and
  `experiments/EXP-002/run_audit.py` (H1, H2). Local `pyproject.toml`, `uv`-managed.
- Run id format: `YYYYMMDDTHHMMSSZ-<git-short-sha>`.
- `runs/EXP-002/<run-id>/` holds `config.json` and `log.txt` at every step, `sanity_check.json`
  from Step 1, and `metrics.json` plus `per_slot.jsonl` (tracked) from Step 2 onward. A Step 1
  run directory therefore has no `metrics.json`.
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
- Nearest-neighbor search space: all train `(service, slot)` instances (O4). The same slot name
  carries different descriptions in different services, and the embedding input includes the
  description.
- "Cosine >= 0.8 under both models" means each model's own nearest neighbor clears 0.8 (O3). The
  two models are not required to pick the same train slot. Whether they do is reported separately
  as top-1 identity agreement.
- Primary metric: % of the population satisfying that condition. Supported if >= 50%, refuted
  if < 50%.
- Reported alongside: per-model rates, the full nearest-neighbor cosine distribution, and the
  % clearing Jaccard >= 0.5.

### H2, one verdict per variant, v1 to v5, with no mean and no all-five requirement
- Population: seen-service slots, N0, primary unit.
- Condition 1 holds for a variant if the exact-name match rate of its slot names against original
  train slot names is **<= 70%**.
- Condition 2 holds for a variant if **>= 80%** of its slots keep cosine >= 0.8 to their own
  original slot under both models.
- A variant is supported only if both conditions hold, and refuted if either fails. Variants that
  pass are usable L1 material (decision rule set by Kapardhi, 2026-10-01).
- Reported alongside, non-deciding: the same two conditions on unseen-service slots, per-variant
  distributions rather than only summary rates, and the computed original-schema baseline rate.

### Embedding-model agreement (reported for H1 and H2, not gating)
- Primary: top-1 identity agreement rate, the share of slots where both models pick the same
  nearest train slot.
- Secondary: Cohen's kappa on the binary cosine >= 0.8 decision.

### Not emitted
No L0 / L1 / L2 / L4 assignment, and no novelty-level label of any kind, appears in
`metrics.json`, `per_slot.jsonl`, or the Result section. Similarity is a covariate (ADR-004,
Proposed). H2's verdicts say which variants are usable L1 material; they do not label any item.

## Leakage check

Not applicable in the training sense: schemas only, no labels, no model trained or prompted.
`test/schema.json` is read, which is schema material and not a label; no dialogue state
annotations are read at any point. StateLM's own `data/splits/test/` is untouched and uncreated.

## Result

**Step 1 gate only. H1 and H2 have not been run.** The experiment record stays at Running.

Run `20261001T172749Z-63641d3`, code commit `63641d3` with a clean tree, seed 0, dataset
commit `e852981ae34990f4358979625854259302feaa78`. Config, per-item evidence and log in
`runs/EXP-002/20261001T172749Z-63641d3/`.

### Gate: PASS

| Measure (N0, instances) | Matched / total | Rate | Band | SGD-X paper | In band |
|---|---|---|---|---|---|
| Slot names | 75 / 116 | 64.66% | 60-70% | 65% | yes |
| Intent names | 20 / 28 | 71.43% | 66-76% | 71% | yes |

Populations: 26 train services, 21 test services, of which 15 unseen and 6 seen. 215 train slot
instances and 53 train intent instances. 116 unseen-service slot instances across 96 unique
names; 28 unseen-service intent instances across 27 unique names.

### Secondary, non-gating

| Kind | Pipeline | Unit | Matched / total | Rate |
|---|---|---|---|---|
| slots | N0 | unique | 55 / 96 | 57.29% |
| slots | N1 | instances | 75 / 116 | 64.66% |
| slots | N1 | unique | 55 / 96 | 57.29% |
| slots | N2 | instances | 76 / 116 | 65.52% |
| slots | N2 | unique | 56 / 96 | 58.33% |
| intents | N0 | unique | 19 / 27 | 70.37% |
| intents | N1 | instances | 20 / 28 | 71.43% |
| intents | N1 | unique | 19 / 27 | 70.37% |
| intents | N2 | instances | 20 / 28 | 71.43% |
| intents | N2 | unique | 19 / 27 | 70.37% |

41 of the 116 unseen-service slot instances have no exact N0 name match in train. That set is
the H1 population.

Normalization observations, for the record: N1 moves no rate for either kind, because SGD slot
names are already lowercase snake_case and intent names are consistently CamelCase on both
sides. Exactly one slot matches under N2 but not N0: 76 - 75 = one, and because normalization is
applied to both sides the N0 matches are a subset of the N2 matches. That slot is
`Buses_3/to_city`, normalizing to "city" against train's `city`, established by a separate
check rather than from the run artifacts, whose `evidence` block holds the N0 cells only. One name, `Trains_1/to`, normalizes to the empty string under N2; no
train slot name does, so it produced no spurious match in this run.

## Interpretation

**What the gate establishes.** One reading of each published statistic lands inside its
pre-registered band: 64.66% against a published 65% for slots, 71.43% against a published 71%
for intents. The agreement should not be quoted more tightly than that, because both published
figures are whole percents and could stand for anything in a half-point either way. The reading
itself is ours: the definition the gate implements is the one recorded in `literature.md`, not a
quotation of the paper's own operationalization, which is still not in this repo. What the gate
licenses is narrow: the pipeline loads the right files, partitions services as specified, and
counts instances correctly, so the machinery H1 and H2 will reuse works to the extent this
tests it.
On SGD's own published labels, roughly two thirds of the slot names in services marked unseen
are literally present in train, which is the condition EXP-002 exists to quantify.

**Threats to validity, in order of how much they matter.**

1. The pass depends on the unit definition, and the secondary unit would have failed. On
   unique names the slot rate is 57.29%, below the 60% band edge. The instance unit was fixed
   as primary in the Setup section by commit `133cd2b`, before `experiments/EXP-002/` existed and
   two commits before the run, so the verdict stands as pre-registered. (An earlier draft of this
   section cited a "Q1" that appears nowhere in the repo; the decision was real but the citation
   pointed at nothing.) The gap is substantive rather than cosmetic: the slot names that repeat
   across unseen services are disproportionately the ones that match train. Any later claim
   about "how much of SGD's unseen set is really unseen" has to name its unit.
2. Resolved by checking, and recorded because an earlier draft of this section got it wrong.
   That draft inferred from the pinned commit's title ("sgdx-intent-bug") that the files behind
   the intent figure had changed after publication. The file history says otherwise:
   `train/schema.json` and `test/schema.json` last changed on 2020-05-07, which predates both
   the SGD-X dataset release (2021-10-20) and the paper. The two files Step 1 read are therefore
   the same ones that existed when SGD-X was published, and the post-publication fix in HEAD
   touches `sgd_x/` files that Step 1 never opened. H2 reads those files, so the concern returns
   there rather than here.
3. Small denominators on the intent side. With 28 intent instances, one intent moves the rate
   by 3.57 points, which is a sizeable fraction of a 10-point band.
4. Exact name matching is the weakest possible notion of overlap, and it is deliberately so
   here. It gives a floor, not a measure of novelty. The 41 non-matching slots are not thereby
   novel: measuring them is H1's job and it has not run.

**What this result does not license.** It says nothing about H1 or H2, which are unmeasured. It
says nothing about whether any slot is semantically novel, only whether its name string occurs
in train. It is not evidence for or against ADR-004, which is about how novelty levels are
assigned, not about how much overlap SGD has. Nothing here contradicts any row in
`docs/research/literature.md`; the SGD-X row is the figure being reproduced.

**Required caveat.** "Novel relative to SGD-train" must never be reported as "unseen by the
model". This experiment compares SGD train schemas against SGD test schemas. It says nothing
about whether a pretrained model has already seen SGD, which remains an open contamination risk
in `docs/research/knowns-unknowns.md`.

Required caveat for any later fill of this section: the paragraph above must appear, in
substance, whenever a result from this experiment is written up.

## Review

`research-reviewer` pass on run `20261001T172749Z-63641d3`, 2026-10-01, after Result and
Interpretation were filled. Verdict: **Sound with caveats**. Its two FAILs were both real and
are fixed above; the sections it passed are listed so the record shows what was actually checked.

### Failed, and what changed

- **Pre-registration, FAIL on one point.** Thresholds themselves verified clean: the record
  revisions (`133cd2b`, `1e4db75`) precede the code commit (`63641d3`), the run id timestamp is
  seconds after it, and `config.json.thresholds` matches `thresholds.py` exactly, including the
  unrun H1 and H2 numbers. But the Interpretation justified the decisive unit choice by citing a
  "Q1" that exists nowhere in the repo. The decision was real and pre-run, recorded in Setup by
  `133cd2b`; the citation pointed at nothing. Replaced with the commit.
- **Claim scope, FAIL on three overclaims.** "Counts what the paper counts" was unverifiable,
  since the paper's own operationalization is not in this repo. "Within 0.34 points" was false
  precision against figures published as whole percents. "Computed on schema files that changed
  after the paper" was inferred from a commit title; checking the file history showed
  `train/schema.json` and `test/schema.json` last changed 2020-05-07, before the SGD-X release.
  The first two were rewritten, the third withdrawn and replaced with the verified fact.

### Passed

Decision linkage (with the coherence problem below), leakage (`config.json.files_read` lists only
the two schema files; no dialogue or annotation file is opened anywhere in the code; `data/splits/`
untouched), generator/judge circularity (no model invoked, `embedding_models: null`),
contamination (no model, and the required caveat is present), label provenance (with the caveat
that the comparison target is partly self-supplied), statistical adequacy (a census of a fixed
population, not a sample, so the >= 3 seeds convention genuinely does not apply), literature
conflict (consistent with the SGD-X row and with `knowns-unknowns.md`).

Also flagged and fixed: the record's own `Status` still read Planned, and Setup listed
`metrics.json` in a Step 1 run directory.

### Independently reconciled against the artifacts

- 75 matched + 41 unmatched = 116 slot instances; 20 + 8 = 28 intent instances. 75/116 =
  64.6552%, 20/28 = 71.4286%. Table, log and JSON agree.
- Verified from the raw files: `train/schema.json` has 26 services and 215 + 53 = 268 slot and
  intent names; `test/schema.json` has 21 services splitting exactly 6 seen / 15 unseen.
- Stronger than the Interpretation stated: 75 - 55 = 20 = 116 - 96, so every duplicated slot
  instance is a matching name. That is the full mechanism behind threat 1.

### Open for the researcher, not fixed here

1. **ADR-004 may already settle what H1 is supposed to inform.** ADR-004 says a test-only SGD
   service is not automatically L2, because we did not hold the field out. If levels come only
   from construction, no overlap measurement can make SGD test services L2, so H1's "whether SGD
   can supply L2 items, or we must construct our own" looks pre-answered by a Proposed ADR.
2. **H2's decision rule selects benchmark material by a measurement.** "Variants that pass are
   usable L1 material" sits in tension with ADR-004's "never by similarity thresholds", and makes
   "L1 is surface-only" partly true by construction.
3. **No contrast condition for the 64.66%.** The matched names are dominated by `price`, `date`,
   `time`, `city`, `address`, `phone_number`, `location`, so the overlap may reflect ordinary
   English field naming rather than anything specific to SGD's split. Adding a contrast after
   seeing the result would be post-hoc, so it is left as a proposal for Step 2 rather than
   computed now.

### One finding not accepted

The review suggested a variant could pass H2 condition 1 by colliding with a different train
slot name. A collision keeps the slot matching train, which holds the exact-match rate up and so
makes condition 1 harder, not easier. The underlying observation still stands as a blind spot
worth recording, in the other direction: a paraphrase that renames a slot onto another train
slot's name looks un-paraphrased to condition 1, which makes that condition conservative.

### Not done, needs a decision

The review's cheapest fix also asks for SGD-X's own definition of its 65% / 71% statistic to be
quoted in `literature.md`. The definition there was supplied by the researcher rather than
quoted from the paper, so closing this means fetching arXiv 2110.06800, which is his call.

## Decision
(pending, human)
