# EXP-002: Schema novelty audit on SGD / SGD-X

Status: Done
Owner: Kapardhi
Created: 2026-10-01
Revised: 2026-10-01 (pre-run, see Change log)
Decision informed:
- H1: whether the benchmark motivation can claim SGD's unseen split overstates semantic novelty,
  beyond SGD-X's lexical finding.
- H2: whether embedding similarity is a valid covariate for ADR-004's stratified reporting.
Blocked by: nothing

## Change log

- **2026-10-01, before any run and before any code existed.** Hypothesis, Metric and
  "Decision informed" revised by Kapardhi. The original hypothesis ("refuted if fewer than ~20%
  of unseen-service slots have a near match at cosine >= 0.8") was unfalsifiable once the
  sanity-check gate passed: exact name matches are, with near certainty though not as a matter of
  arithmetic, also near matches under the cosine measure, so a gate asserting ~65% exact matches
  over the same population left no realistic path to a <20% result. (The qualifier matters: the
  embedding input carries each slot's description, so identical names do not strictly guarantee
  cosine >= 0.8. The original wording claimed arithmetic it did not have.) Replaced by H1 and H2,
  which are evaluated on populations the gate does not already determine. At the time of this
  change no run had been executed, no metric had been computed, and `experiments/EXP-002/` did
  not exist.
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

- **2026-10-01, after the Step 1 gate result was seen.** Four changes by Kapardhi, made with the
  gate numbers (64.66% slots, 71.43% intents) already in view. The gate itself is untouched: no
  threshold, population or measurement it used has changed, and it has not been re-run.
  1. **The SGD-X paper's own wording is now quoted** in `literature.md`: the sentence defining
     the 65% / 71% figures, the three statements establishing the v1-v5 ordering, and Table 1.
     This changes no EXP-002 number. It settles one open question in the gate's favour without
     the gate bearing on it: the paper does not state its unit, and only the pre-registered
     instance reading reproduces both figures.
  2. **H1's "Decision informed" rewritten** to "whether the benchmark motivation can claim SGD's
     unseen split overstates semantic novelty, beyond SGD-X's lexical finding." H1's population,
     measurement and thresholds are unchanged and H1 has not run, so this changes what an unrun
     result will be used to argue, not what will be measured. The gate measures exact-name
     overlap and says nothing about semantic novelty, so it cannot inform this.
  3. **H2 replaced entirely**, now that ADR-004 is accepted: the old H2 selected L1 material by
     measurement, which ADR-004 forbids. The old H2 had not run. Its thresholds (<= 70% exact
     match, >= 80% retained) are retired rather than moved, because the new H2 measures a
     different quantity, on a different population, for a different decision. The gate read only
     original SGD schemas and no SGD-X file, so it bears on neither version.
  4. **An exploratory section added** for the frequency of the shared slot names behind the
     64.66%. Unlike the other three, this one *is* prompted by the gate result. That is exactly
     why it carries no hypothesis and no threshold and is labelled exploratory wherever it
     appears: a statistic chosen after seeing the number it describes cannot test anything.

- **2026-10-01, pre-run, prompted by SGD-X Table 1 and by no H2 data.** H2's refutation rule
  changed by Kapardhi. Strict monotonicity of the five per-variant means is replaced by two
  conditions that must both hold under both embedding models: a one-sided paired Wilcoxon
  signed-rank test on per-slot cosine, v5 below v1, at p < 0.01; and Spearman rho between variant
  index and mean cosine <= -0.9, which tolerates at most one adjacent inversion. What prompted it
  was the paper's own Table 1, quoted in `literature.md`, where the % of test slot names seen in
  train runs 13, 14, 5, 6, 2 across v1-v5 and so is itself non-monotone. No H2 measurement
  existed when this changed: neither embedding model had been loaded, `per_slot.jsonl` did not
  exist, and no cosine had been computed. Strict monotonicity is kept as a reported,
  non-deciding output, so the stricter reading stays visible in the results.
- **2026-10-01.** ADR-004 moved from Proposed to Accepted on Kapardhi's instruction, so this
  record now cites it as settled rather than proposed.

- **2026-10-01, pre-run implementation note on H2 condition (b).** The rule as written is
  "Spearman rho <= -0.9, which allows at most one adjacent inversion". Those two clauses agree in
  exact arithmetic but not in floating point: with n = 5 a single adjacent inversion gives
  rho = -0.9 exactly on paper, and -0.8999999999999998 when computed, which is 2.2e-16 **above**
  the bound. A bare `rho <= -0.9` would therefore reject the one case the rule explicitly admits.
  Condition (b) is evaluated as `rho <= -0.9 + 1e-9`, which honours the written rule rather than
  loosening it: the next configuration, two adjacent inversions, gives rho = -0.8 and is still
  rejected by a margin of 0.1. Recorded before any H2 data existed and pinned by a test that
  asserts the hazard directly, in `thresholds.spearman_meets_bound`.

## Hypothesis

**Gate (pre-condition, not a hypothesis).** The SGD-X exact-name overlap figures reproduce inside
the bands in Metric below. If they do not, the experiment stops and reports. H1 and H2 are not
evaluated and no similarity work is done.

**H1 (semantic near-duplication beyond exact matches).** Among slots in unseen test services that
have **no exact name match** in train, a majority (>= 50%) have a nearest train slot at
cosine >= 0.8 under **both** embedding models. Refuted if < 50%.

**H2 (covariate validity), evaluated across all five SGD-X variants.** All five variants are L1
**by construction** under ADR-004: human-validated crowdsourced paraphrases of schemas present in
train. No variant is selected, excluded or relabelled by any measurement. H2 asks whether
embedding similarity tracks that construction ordering: cosine to a slot's own original slot
falls from v1 to v5, tested per slot and across variants, under **both** embedding models.
Supported only if both conditions in Metric hold under both models; refuted if either fails under
either model.

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

### SGD-X variants: construction status, pairing, and validation
- **All five variants are L1 by construction** (ADR-004): human-written, manually vetted
  crowdsourced paraphrases, quoted in `literature.md`. Nothing in this experiment selects,
  excludes or relabels a variant by a measurement.
- **Conflict with ADR-004, surfaced by the second review and since resolved by the dated
  amendment under Decision**, which rules that only the 44 seen-service pairs are L1 by
  construction and that paraphrases of test-only services receive no novelty level. The conflict
  as it stood: ADR-004's rule is "paraphrase of a schema present in **train** -> L1", and it
  calls SGD-X variants "candidate L1 material". The population implemented here is every slot of
  every test service, which is 44 slot pairs from the 6 services that are in train and 116 from
  the 15 that are not. So 72.5% of the pairs are paraphrases of schemas absent from train, whose
  construction label is undefined under ADR-004 rather than L1. An earlier version of H2 was
  restricted to seen-service slots for exactly this reason; the replacement did not restate a
  population and the implementation widened it without flagging the change. See the diagnostic
  in Result and the open item in Review.
- The paper's ordering claim, quoted in `literature.md`, is that v1 is closest to the original
  and v5 farthest, with paraphrases sorted by increasing Levenshtein distance on names and
  increasing Jaccard distance on descriptions. That ordering is established on **surface**
  metrics; H2 asks whether it survives in embedding space, which construction does not guarantee.
- H2 population: every slot of every service in each variant's test schema, paired 1:1 with its
  own original slot. No filtering.
- **Pairing key.** SGD-X renames services: a variant's `service_name` is the original name with
  the variant index appended (`Alarm_1` -> `Alarm_11` in v1, `Alarm_15` in v5), and the same
  applies to its train schemas. The key is therefore `(original service_name, position in that
  service's slot list)`, with the original name recovered by stripping the suffix. An earlier
  draft keyed on `(service_name, position)` directly, which would have paired nothing at all.
- **Validation before H2 is computed**, failing loudly rather than mismatching silently: for each
  variant, the service list must have the same length and order as the original, every variant
  `service_name` must equal its original name with the variant index appended, and every service
  must carry the same slot count. If any check fails the run stops. The run's check covers those
  three things and not intent counts, which H2 does not use; intent counts were confirmed to
  match separately, outside the run, when this section was written. The validation checks slot
  counts, not that position j of a variant is a paraphrase of position j of the original; spot
  checks in `per_slot.jsonl` (`alarm_time` -> `clock_time_of_alarm`, `to_station` ->
  `arrival_station_name`) show the correspondence holds in fact.

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

### H2, covariate validity across all five variants
- Population: every slot of every service in each variant's test schema, paired 1:1 with its own
  original slot. Nothing is filtered by a measurement.
- H2 is **supported** only if both conditions below hold under **both** embedding models, and
  **refuted** if either fails under either model:
  - **(a) v5 sits below v1, per slot.** One-sided paired Wilcoxon signed-rank test across slots
    on the cosine of each slot to its own original, v5 against v1, alternative "v5 is lower".
    Holds at **p < 0.01**.
  - **(b) the trend is near-monotone.** Spearman rho between variant index (1 to 5) and
    per-variant mean cosine is **<= -0.9**. The bound is inclusive and exact rather than
    approximate: with n = 5, a perfectly decreasing order gives rho = -1.0 and a single adjacent
    inversion gives rho = exactly -0.9, so "<= -0.9" admits at most one adjacent inversion.
- Reported, non-deciding: the per-variant cosine distributions rather than only the means, the
  strict-monotonicity check (whether the five means are strictly decreasing) which was the
  previous deciding rule, the Wilcoxon statistic alongside its p-value, and the paired per-slot
  cosines in `per_slot.jsonl`.
- Documented prior, from the Table 1 figures quoted in `literature.md`: the paper's own surface
  statistic (% of test slot names seen in train) is **not** monotone across variants (13%, 14%,
  5%, 6%, 2%, with v2 above v1 and v4 above v3). A strict monotonicity test on a mean can
  therefore fail even where the construction ordering holds in its own metric. A refutation would
  say that embedding cosine does not track the construction order, which is the question, not
  that the variants are misordered.

### Embedding-model agreement (reported for H1 and H2, not gating)
- Primary: top-1 identity agreement rate, the share of slots where both models pick the same
  nearest train slot.
- Secondary: Cohen's kappa on the binary cosine >= 0.8 decision.

### Not emitted
No L0 / L1 / L2 / L4 assignment, and no novelty-level label of any kind, appears in
`metrics.json`, `per_slot.jsonl`, or the Result section. Similarity is a covariate (ADR-004).
H2 assigns nothing either: the variants' L1 status comes from how they were built, and H2 only
asks whether the covariate tracks it.

## Exploratory, post-hoc: frequency of the shared slot names

**Exploratory.** Added after the Step 1 gate result was seen. No hypothesis, no threshold, no
verdict. Nothing in this section tests anything, and no number from it may be reported as support
for or against H1, H2, or any ADR.

What it computes, for the 75 matched unseen-service slot instances: how often each shared name
occurs, how many distinct unseen services carry it, and how many distinct train services carry it.
The output is a frequency table, labelled exploratory in `metrics.json`, in any figure, and in any
write-up that uses it.

Why it exists: the matched names are visibly dominated by generic field vocabulary (`price`,
`date`, `time`, `city`, `address`, `phone_number`, `location`), which raises the question of
whether the 64.66% reflects SGD's split or ordinary English field naming. That question needs a
contrast condition designed in advance. This section describes the shape of the overlap; it does
not answer that question, and it was chosen after seeing the result it describes.

## Leakage check

Not applicable in the training sense: schemas only, no labels, no model trained or prompted.
`test/schema.json` is read, which is schema material and not a label; no dialogue state
annotations are read at any point. StateLM's own `data/splits/test/` is untouched and uncreated.

## Result

All of Steps 0 to 3 have run. **Gate PASS, H1 REFUTED, H2 SUPPORTED under both models.**

### Pre-registration check

No threshold was changed after seeing the result it judges. Commit times against run ids:
the H2 refutation rule landed in `7fc8825` at 17:52:45, the code carrying it and the float
tolerance in `df17cad` at 17:58:04, and the audit ran at 17:58:11 and again at 18:00:31. Every
number in `config.json.thresholds` matches `thresholds.py` at the commit the run records.

### Step 1 gate: PASS

Run `20261001T172749Z-63641d3`, code commit `63641d3` with a clean tree, seed 0, dataset
commit `e852981ae34990f4358979625854259302feaa78`. Config, per-item evidence and log in
`runs/EXP-002/20261001T172749Z-63641d3/`.

#### Gate figures

| Measure (N0, instances) | Matched / total | Rate | Band | SGD-X paper | In band |
|---|---|---|---|---|---|
| Slot names | 75 / 116 | 64.66% | 60-70% | 65% | yes |
| Intent names | 20 / 28 | 71.43% | 66-76% | 71% | yes |

Populations: 26 train services, 21 test services, of which 15 unseen and 6 seen. 215 train slot
instances and 53 train intent instances. 116 unseen-service slot instances across 96 unique
names; 28 unseen-service intent instances across 27 unique names.

#### Secondary, non-gating

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
`Buses_3/to_city`, normalizing to "city" against train's `city`, established by a separate check
rather than from the run artifacts, whose `evidence` block holds the N0 cells only. One name,
`Trains_1/to`, normalizes to the empty string under N2; no train slot name does, so it produced
no spurious match in this run.

### Steps 2 and 3: H1 and H2

Run `20261001T180031Z-746c803`, code commit `746c803` with a clean tree, seed 0, same dataset
commit. Models, pinned by resolved commit sha and recorded in `config.json`:
`sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` and
`BAAI/bge-base-en-v1.5` @ `a5beb1e3e68b9ab74eb54cfd186867f64f240e1a`. An earlier run of the same
code path, `20261001T175811Z-df17cad`, produced identical means and identical verdicts; it is
kept rather than deleted. It is superseded because it stored Spearman rho rounded to six decimal
places, which printed as exactly -0.9 and hid the quantity that decides H2, and also because it
lacks `would_hold_without_float_tolerance`, `rho_6dp` and `adjacent_inversions`. An earlier draft
of this paragraph said "only because it stored rho rounded", which understated what the second
run added: that commit landed after the first H2 numbers were visible, and what it added was
disclosure.

All five SGD-X variants passed the structural validation: 21 test services in the original
order, every variant service name equal to its original plus the variant index, matching slot
counts throughout.

#### H1: REFUTED

5 of 41 = **12.20%** of the H1 population clear cosine 0.8 under both models, against a
pre-registered threshold of >= 50%. Search space 215 train `(service, slot)` instances.

| Model | Clears 0.8 | Mean nearest cosine | p10 / p50 / p90 |
|---|---|---|---|
| all-MiniLM-L6-v2 | 12.20% (5/41) | 0.6131 | 0.423 / 0.593 / 0.805 |
| bge-base-en-v1.5 | 41.46% (17/41) | 0.7747 | 0.689 / 0.781 / 0.856 |

Both point estimates sit below the 50% threshold, but they are not equally far from it. Wilson
95% intervals, computed post-hoc because no interval was pre-registered: MiniLM
[5.3%, 25.5%], BGE **[27.8%, 56.6%]**, which covers 50%. Nearest train slot by Jaccard clears
0.5 for 39.02%. Model agreement: top-1 identity 56.10%, Cohen's kappa on the 0.8 decision 0.328.
The both-models rate equals MiniLM's exactly, so MiniLM's 5 clearing slots are a subset of
BGE's 17.

#### H2: SUPPORTED under both models

160 slot pairs per variant, the full test population, paired 1:1 with their own originals.

| Model | v1 | v2 | v3 | v4 | v5 | (a) Wilcoxon p | (b) rho | Inversions | Strictly decreasing |
|---|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.8012 | 0.7752 | 0.7384 | 0.7346 | 0.7351 | 5.53e-11 | -0.8999999999999998 | 1 | no |
| bge-base-en-v1.5 | 0.8819 | 0.8617 | 0.8421 | 0.8320 | 0.8359 | 4.98e-14 | -0.8999999999999998 | 1 | no |

Condition (a) holds decisively under both models. Condition (b) holds in both cases **through
the pre-run float tolerance and not without it**: both models land on exactly one adjacent
inversion, v4 to v5, so raw rho is -0.8999999999999998 and
`would_hold_without_float_tolerance` is `false` for both. The inversions are small: +0.000483
for MiniLM and +0.003926 for BGE. Neither model produces strictly decreasing means, so the
replaced rule would have refuted H2 under both. Wilcoxon statistics, which the Metric section
lists as reported: 2653.0 for MiniLM and 2072.0 for BGE.

Per-variant distributions, also promised in Metric and not only as means (p10 / p50 / p90):

| Model | v1 | v2 | v3 | v4 | v5 |
|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | .670/.816/.920 | .644/.804/.887 | .607/.749/.877 | .577/.744/.868 | .576/.747/.887 |
| bge-base-en-v1.5 | .820/.890/.943 | .795/.869/.925 | .760/.852/.913 | .744/.840/.912 | .742/.845/.916 |

#### Post-hoc diagnostics, deciding nothing

Two reference figures computed after the verdicts, from this run's own `per_slot.jsonl`. Neither
was pre-registered, neither changes any verdict, and neither may be quoted as a test.

**1. H2 restricted to the 44 seen-service pairs**, the only ones that are L1 under ADR-004's
rule. The verdict **reverses**:

| Model | v1 | v2 | v3 | v4 | v5 | (a) p | (b) rho | Verdict on this population |
|---|---|---|---|---|---|---|---|---|
| all-MiniLM-L6-v2 | 0.7760 | 0.7503 | 0.7018 | 0.7001 | 0.7184 | 0.0027 | -0.7 | REFUTED |
| bge-base-en-v1.5 | 0.8789 | 0.8523 | 0.8298 | 0.8223 | 0.8335 | 9.45e-05 | -0.7 | REFUTED |

Condition (a) still holds on this population; condition (b) fails under both models. Note the
mechanism: `adjacent_inversions` is 1 in both cases, but v5 rises above both v4 and v3, so the
displacement spans two rank positions and Spearman reads -0.7 rather than -0.9.

**2. A calibration reference for H1's 0.8 cutoff.** H2's pairs are known same-slot paraphrases,
so their cosines say what the cutoff means in each model's geometry:

| Model | v1 paraphrases below 0.8 | v5 paraphrases below 0.8 |
|---|---|---|
| all-MiniLM-L6-v2 | 67/160 = 41.9% | 111/160 = 69.4% |
| bge-base-en-v1.5 | 9/160 = 5.6% | 42/160 = 26.2% |

#### Exploratory, post-hoc, deciding nothing

75 matched instances across 55 distinct shared names. Most frequent: `phone_number` (4
instances, 4 unseen services, 9 train services), then `address`, `city`, `genre`, `location`
and `price` at 3 instances each.

## Interpretation

### Step 1 gate

**What the gate establishes.** One reading of each published statistic lands inside its
pre-registered band: 64.66% against a published 65% for slots, 71.43% against a published 71%
for intents. The agreement should not be quoted more tightly than that, because both published
figures are whole percents and could stand for anything in a half-point either way. The paper's
own sentence is now quoted in `literature.md`, and it does not state its unit, so the reading is
still ours. What has changed is that the evidence now favours it: the pre-registered instance
reading reproduces both figures, while the unique-name reading reproduces neither. What the gate
licenses is narrow: the pipeline loads the right files, partitions services as specified, and
counts instances correctly, so the machinery H1 and H2 will reuse works to the extent this tests
it. On SGD's own published labels, roughly two thirds of the slot names in services marked unseen
are literally present in train, which is the condition EXP-002 exists to quantify.

**Threats to validity, in order of how much they matter.**

1. The pass depends on the unit definition, and the secondary unit would have failed. On
   unique names the slot rate is 57.29%, below the 60% band edge. The instance unit was fixed
   as primary in the Setup section by commit `133cd2b`, before `experiments/EXP-002/` existed and
   two commits before the run, so the verdict stands as pre-registered. (An earlier draft of this
   section cited a "Q1" that appears nowhere in the repo; the decision was real but the citation
   pointed at nothing.) The gap is substantive rather than cosmetic: the slot names that repeat
   across unseen services are disproportionately the ones that match train. Quoting the paper
   softens this without removing it: its sentence is ambiguous on the unit, and only the
   pre-registered reading reproduces both published figures, so the choice is now evidenced
   rather than merely declared. The unique-name reading would still fail the band, so any later
   claim about "how much of SGD's unseen set is really unseen" has to name its unit.
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

### H1: refuted under the pre-registered rule, and carried by one model

**What it shows.** Among the 41 unseen-service slots whose names do not appear in train, 12.20%
have a nearest train slot at cosine >= 0.8 under both models, against a pre-registered 50%. H1
is refuted under its rule as written. An earlier draft of this section called the refutation
"robust in direction" on the grounds that both models fall below 50% individually; the second
review was right that this overstates it, and it is withdrawn. The split verdict is:

- **MiniLM refutes H1 decisively**: 5/41, Wilson 95% [5.3%, 25.5%], nowhere near the threshold.
- **BGE does not refute H1; it fails to support it**: 17/41 = 41.46%, four items short, Wilson
  95% [27.8%, 56.6%], an interval that covers 50%. At n = 41 its point estimate is not
  distinguishable from the threshold.
- The headline 12.20% **is MiniLM's number**. The conjunction's rate equals it exactly because
  MiniLM's clearing set is a subset of BGE's, so 12.20% must never be quoted without saying it
  is the lower-scaled encoder's figure.

So the finding is: the slots surviving the exact-name filter are not mostly semantic
near-duplicates of train fields under the stricter-scaled encoder, and the more permissive
encoder leaves the question open.

**What that means for the decision it informs.** The benchmark motivation cannot claim, on this
evidence, that SGD's unseen split overstates *semantic* novelty beyond SGD-X's lexical finding.
The lexical finding stands and is ours to cite: 64.66% of unseen-service slot names are literally
present in train. The residue is a different matter, and H1 predicted it would also be
redundant. It is not. The defensible claim is therefore narrower than the one H1 was written to
support: SGD's "unseen" label is lexically leaky, and we have no evidence that what remains after
removing the exact matches is semantically redundant too.

**Threats, in order of how much they matter.**

1. **The 0.8 cutoff is uncalibrated, and under MiniLM it is stricter than a genuine paraphrase
   of the same slot.** This is the largest problem with H1 as designed, and the run contains its
   own reference distribution. H2's pairs are known same-slot paraphrases, and under MiniLM
   41.9% of the closest ones (v1) and 69.4% of the most distant (v5) fall **below** 0.8; under
   BGE the same figures are 5.6% and 26.2%. So H1 asked whether a majority of merely *similar*
   slots clear a bar that identity-preserving rewordings only half clear under the model that
   pins the conjunction. That is close to unachievable by construction, which is the mirror image
   of the unfalsifiability problem the Change log records for the original H1.
   The scale difference is systematic: mean nearest cosine 0.7747 against 0.6131, p10 0.689
   against 0.423, and in H2 BGE's variant means run 0.83 to 0.88 where MiniLM's run 0.73 to 0.80.
   What does not survive is not merely the magnitude but, under BGE, the **verdict**: its median
   nearest cosine is 0.781, so a cutoff of 0.75, no more arbitrary than 0.8, would put it above
   50%. No per-model calibration was pre-registered, and none should be introduced now.
2. **Small population.** n = 41, so one slot moves the rate by 2.44 points. BGE, the more
   permissive model, is four slots short of the threshold. The refutation is not a rounding
   artifact, but for that model it is not a wide margin either.
3. **The nearest train slot is not a stable object across models.** Top-1 identity agreement is
   56.10% and Cohen's kappa on the 0.8 decision is 0.328. The two models often disagree about
   which train field is closest, which bears directly on any later use of "nearest train field"
   as a per-item covariate.
4. **"Both models" is a weak independence claim.** Both are English web-trained sentence
   encoders, as the earlier review noted. Their disagreement here makes that point sharper
   rather than softer: two models of the same family already diverge this much.

### H2: supported, at the exact boundary of its rule

**What it shows.** Under both models, cosine to a slot's own original falls from v1 to v5, and
both conditions hold. Condition (a) is decisive: the one-sided paired Wilcoxon puts v5 below v1
at p = 5.5e-11 and 5.0e-14 over 160 pairs. Condition (b) holds, but only just, and only through
the float tolerance: both models land on exactly one adjacent inversion, at the same place
(v4 to v5), so raw rho is -0.8999999999999998 and the bare comparison fails. The rule as written
admits exactly one adjacent inversion, and the data landed on exactly that case.

**The pre-registration question a reader should ask, answered.** H2's verdict depends on two
decisions that both favour support: replacing strict monotonicity, and tolerating the float
boundary. Neither was made after seeing an H2 number. The strongest evidence is not the commit
log but the artifacts: the superseded run's `metrics.json`, written at 17:58:11, already records
`"float_tolerance": 1e-09`, so the tolerance was in the executing code at the first H2 run and
was not retrofitted. The hazard test uses synthetic values and is data-independent. And the
substantive defence stands on its own: `rho <= -0.9 + 1e-9` restores an inclusive `<= -0.9`
exactly, and a 1e-9 slack against the 0.1 gap to the next configuration cannot admit anything
the written bound did not already include. An earlier draft of this paragraph said "the defence
is the commit order, not the argument"; that was backwards, and the second review was right to
invert it. Commit times (`7fc8825` 17:52:45, `df17cad` 17:58:04, runs at 17:58:11 and 18:00:31)
are self-reported metadata from one clock and one actor, so they are the weaker half. Under the
replaced rule, H2 would have been refuted under both models.

**What H2 actually measured, which is narrower than its stated decision.** H2 computes the cosine
of each variant slot to **its own original test slot**. ADR-004 defines the covariate as
"embedding similarity to the nearest **train** field". These are different quantities, and no
variant-against-train comparison exists in this run: `config.json.files_read` contains no variant
train schema. So H2 validates cosine as a measure of *paraphrase distance from a slot's own
original*, and it does not test the nearest-train-field covariate that ADR-004 stratifies by. The
"Decision informed" line claims more than the measurement supports, and correcting it is the
researcher's call, not something to be quietly reworded here.

**The population is also narrower than the L1 premise.** 116 of the 160 pairs are paraphrases of
test services absent from train, which ADR-004's rule does not make L1. On the 44 pairs that are
L1 under that rule, **H2 reverses: refuted under both models**, rho = -0.7, with condition (a)
still holding. So H2's supported verdict is specific to a population three quarters of which sits
outside the premise the hypothesis states. That diagnostic is post-hoc and decides nothing by
itself; which population H2 should have been registered on is an open item for the researcher.

**What can be said about the covariate, with those limits.** On the full test population,
distance from a slot's own original tracks the construction order coarsely and not finely: v1
against v5 is decisive, and v4 against v5 inverts under both models by 0.0005 and 0.0039. The
rule's gloss "at most one adjacent inversion" equals rho = -0.9 only when the inversion is a pure
swap of neighbouring ranks, which is what happened here; the 44-pair diagnostic shows a single
inversion spanning two rank positions reads -0.7 instead, so "one inversion" and "rho = -0.9" are
not interchangeable.

**The cross-model pattern is the more useful finding.** The two models agree closely on
*ordering* (identical rho, the same inversion in the same place) while disagreeing sharply on
*absolute* values (H1: 12% against 42% at the same cutoff). For ADR-004 that distinction is
actionable: a covariate used as a rank is reproducible across these two encoders, a covariate
used against a fixed cutoff is not.

**Threats.**

1. **The cosine conflates two axes the construction kept apart.** The embedding input is
   `"{name}: {description}"` and SGD-X paraphrases both, while the paper ordered variants by
   Levenshtein on names and Jaccard on descriptions *separately*. A single cosine cannot say
   which axis drives the trend, or which one causes the v4/v5 inversion.
2. **160 pairs is a census, not a sample.** The p-values describe this population of test
   schemas. They do not license an inference to other schemas, and nothing here has been
   measured on a second dataset.
3. **The v4/v5 inversion may be an artifact of the source construction.** The paper selected 5
   paraphrases at random where more than 5 existed, so adjacent variants need not be separated
   by a consistent margin. We cannot check that from the released files.
4. **Variant train schemas were not read.** H2 pairs variant test slots against their own
   originals, so the post-publication `sgd_x` fix in the pinned commit touches files this run
   did read. The fix concerned intents; H2 measures slots, and no intent figure is computed here.
5. **The 160 slots are treated as independent and are not.** They are nested in 21 services and
   were paraphrased per schema element, so the Wilcoxon's effective sample size is smaller than
   its nominal one. The p-values are extreme enough that the direction is unlikely to be an
   artifact of this, but no clustered or service-level test was pre-registered or run.
6. **No interval was pre-registered on any deciding number.** H1's verdict turns on a proportion
   at n = 41 and H2's condition (b) on adjacent mean gaps of 0.0005 to 0.004 against a per-slot
   spread of roughly 0.11 from p10 to p90. The Wilson intervals in Result are post-hoc, and no
   standard error or bootstrap was computed for the H2 means. A gap three orders of magnitude
   below the spread it is drawn from should not be read as a measured difference.
7. **Encoder contamination is unaddressed, and it is the channel that could move these numbers.**
   Every figure in Steps 2 and 3 is encoder geometry. SGD has been public since 2019 and SGD-X
   since 2021, so both model families may have seen these schemas in pretraining. The required
   caveat below covers the task model; it does not cover the measurement instruments.

### Exploratory, post-hoc

Nothing in that section tests anything, and no direction should be read off it. It describes
the shape of the overlap: 55 distinct names behind 75 instances, topped by `phone_number`,
`address`, `city`, `genre`, `location`, `price`. An earlier draft added that this "is consistent
with" the overlap reflecting ordinary field naming; that sentence is removed, because a
post-hoc description cannot support a direction even with a retraction attached. Whether generic
field naming explains the 64.66% is open, and the contrast condition that could settle it was
deliberately not built after the fact.

### What these results do not license

H1's refutation does not say the 41 slots are novel in any absolute sense; it says they are not
near-duplicates of train fields under two specific encoders at one specific uncalibrated cutoff.
H2's support does not say cosine is a good covariate, only that it tracks the construction
ordering coarsely under both models, and it does not license using cosine to assign or order
novelty levels, which ADR-004 forbids regardless of any measurement. The gate says nothing about
semantic novelty at all. Nothing in this experiment speaks to whether SGD's unseen split is hard
for a model, because no model was asked to do the task. Nothing here contradicts any row in
`docs/research/literature.md`.

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

### Closed after the review

The review's remaining cheapest-fix item, quoting SGD-X's own definition of its 65% / 71%
statistic, is done: arXiv:2110.06800v3 was fetched and the sentence, the ordering statements and
Table 1 are quoted in `literature.md`. The paper turns out not to specify the unit, and only the
pre-registered instance reading reproduces both figures.

Its first open item is resolved by ADR-004 being accepted and H2 being replaced: nothing in this
experiment now selects benchmark material by a measurement. Its third item, the missing contrast
condition for the 64.66%, is addressed only in the weak sense that an exploratory, post-hoc
frequency breakdown now exists; a designed-in-advance contrast remains unbuilt.

### Second pass, 2026-10-01, after Steps 2 and 3

`research-reviewer` on the full record. Verdict: **Sound with caveats** for the gate and H1,
**Not interpretable as stated** for H2. Four checks failed and all four were real; every fix
below is prose, and no verdict, threshold or measurement was changed.

**Its most serious finding, confirmed against the data.** H2's supported verdict was presented as
licensing embedding similarity as ADR-004's covariate, but it measured similarity to each slot's
own *test* original rather than to the nearest *train* field, which is what ADR-004 defines; and
116 of its 160 pairs are paraphrases of services absent from train, so ADR-004's rule does not
make them L1. Verified: 44 seen-service pairs, 116 unseen-service pairs, 72.5%. Restricted to the
44 that are L1, **H2 reverses to refuted under both models** (rho = -0.7). Recorded as a post-hoc
diagnostic in Result and as an open item below.

**Other failures, all fixed in prose.**

- *Claim scope.* "Refuted, and robustly in direction" overstated H1; withdrawn for a split
  verdict naming BGE's Wilson interval [27.8%, 56.6%], which covers 50%.
- *Baseline validity.* The 0.8 cutoff had no reference distribution, and the run contained one
  that contradicts it: under MiniLM, 41.9% of known same-slot paraphrases at v1 and 69.4% at v5
  fall below 0.8. H1's bar was stricter than a genuine paraphrase under the model that pins the
  conjunction. Now recorded as threat 1 with the numbers.
- *Statistical adequacy.* No interval was pre-registered on any deciding number, and H2's
  condition (b) is adjudicated by gaps three orders of magnitude below the spread they come from.
  Added as threats 5 and 6, with the Wilson intervals marked post-hoc.
- *Contamination.* The required caveat covers the task model, not the encoders. SGD has been
  public since 2019 and SGD-X since 2021, and every Step 2-3 number is encoder geometry. Added
  as threat 7.
- The claim that the earlier run was superseded "only because" of rounding was false; it also
  gained three disclosure fields, in a commit made after the first numbers were visible.
- "The defence is the commit order, not the argument" was backwards. The argument is the sound
  defence; commit metadata from one clock and one actor is the weaker half. Inverted, and the
  stronger artifact-side proof is now cited: the superseded run's `metrics.json`, written at
  17:58:11, already records `float_tolerance: 1e-09`.
- Setup claimed the run's validation checks intent counts; it checks service count, the suffix
  rule and slot counts. Corrected, with the separate intent check attributed to where it happened.
- The Wilcoxon statistics and the per-variant distributions, both promised in Metric, were only
  in `metrics.json`. Now in Result.
- One inferential sentence in the exploratory subsection was removed rather than retracted
  in place.

**What it verified independently.** Every number in Result reconciles exactly with
`metrics.json`, including all ten H2 means, both raw rho values, the inversion counts, the
quantiles, the agreement figures and the exploratory table's sum. It re-derived Cohen's kappa by
hand, confirmed the superseded run has identical means, converted the reflog epochs by hand to
check the claimed commit times, and confirmed the arithmetic that one adjacent rank swap gives
rho = -0.9 exactly while two give -0.8. It found the Wilcoxon correctly oriented and pinned by a
test that would fail if inverted, and the tie-breaking deterministic.

**Governance finding, accepted.** Commit `7fc8825` bundled the H2 threshold change with accepting
ADR-004 and with editing CLAUDE.md's ADR-status rule. All three were instructed, but bundling a
rule change that loosens a constraint on me with a threshold a verdict depends on is poor
hygiene; it should have been three commits.

### Open for the researcher, from the second pass

1. **Which population H2 should be registered on.** *Answered by the dated amendment under
   Decision: only the 44 seen-service pairs are L1 by construction, paraphrases of test-only
   services receive no novelty level and are not used as leveled benchmark material, and the H2
   verdict is unaffected.* As it stood: the seen-service restriction was removed without being
   flagged, and the verdict depends on it, supported on 160 pairs and refuted on the 44 that
   ADR-004 calls L1.
2. **H2's "Decision informed" line.** It claims the ADR-004 covariate, which is defined against
   the nearest train field and was not measured. The wording is the researcher's.
3. **Whether H1 is worth re-registering with a calibrated cutoff.** Under MiniLM the 0.8 bar is
   stricter than a same-slot paraphrase, so the refutation is partly structural. No threshold
   should be changed on this record; this would be a new experiment.

## Decision

Transcribed from Kapardhi, 2026-10-01.

Gate: reproduced. The per-instance unit is adopted as the reading of SGD-X's figures.

H1 refuted (12.2% both-model; 41.5% BGE alone; both below 50%; n=41). The benchmark
motivation will cite SGD's lexical leakage only and will not claim semantic
redundancy. SGD test-only services are not used as L2 material; L2 items will be
constructed (ADR-004).

H2 supported under the pre-registered rule, at its boundary: exactly one adjacent
inversion (v4/v5) under both models. v1 vs v5 separation is strong (p < 1e-10).
Adjacent variants are not separable by cosine. Embedding similarity is accepted as a
coarse covariate only: within-model ranks or strata, at least two encoders, no
absolute cutoffs. Recorded as ADR-005 (Proposed).

All five SGD-X variants are usable L1 material by construction (ADR-004).

### Amendment

Transcribed from Kapardhi, 2026-10-01.

Amendment, 2026-10-01: The final sentence overstated. Under ADR-004, only SGD-X
paraphrases of services present in train/schema.json (44 of 160 pairs per variant)
are L1 by construction. Paraphrases of test-only services receive no novelty level and
are not used as leveled benchmark material. The H2 verdict is unaffected.
