# Handoff: 2026-10-01 · EXP-002 schema novelty audit on SGD / SGD-X

## Done
- EXP-002 Steps 0-3. Record: `docs/research/experiments/EXP-002-schema-novelty-audit.md`.
  Code: `experiments/EXP-002/`. Runs: `runs/EXP-002/`. 134 tests.
- Dataset pinned to `dstc8-schema-guided-dialogue` @ `e852981`; 18 schema files in
  `data/raw/sgd/<commit>/`, SHA-256 per file in each run config.
- ADR-004 set to Accepted on instruction. ADR-005 drafted, Status: Proposed.
- `literature.md`: arXiv:2110.06800v3 quoted (65%/71% sentence, three ordering statements,
  Table 1, crowdsourcing and manual-vetting passages).
- `CLAUDE.md` and `docs/research/adr/README.md`: ADR-status rule refined; rule 5 now permits
  transcribing a Decision verbatim. Decision and its dated amendment transcribed.

## Results (numbers only)
- Gate, run `20261001T172749Z-63641d3`, seed 0, N0, instances: slots 75/116 = 64.66%
  (band 60-70, published 65); intents 20/28 = 71.43% (band 66-76, published 71).
  Secondary unique-name unit: slots 55/96 = 57.29%; intents 19/27 = 70.37%.
- H1, run `20261001T180031Z-746c803`, n=41, search space 215, threshold >= 50%:
  both-model 5/41 = 12.20%. MiniLM 5/41 = 12.20%, Wilson 95% [5.3, 25.5].
  BGE 17/41 = 41.46%, Wilson 95% [27.8, 56.6]. Jaccard >= 0.5: 39.02%.
  Top-1 identity 56.10%, Cohen's kappa 0.328.
- H2, same run, 160 pairs per variant. MiniLM means v1-v5: 0.8012, 0.7752, 0.7384, 0.7346,
  0.7351; Wilcoxon p = 5.53e-11, stat 2653.0; rho = -0.8999999999999998; inversions 1.
  BGE means: 0.8819, 0.8617, 0.8421, 0.8320, 0.8359; p = 4.98e-14, stat 2072.0; rho identical;
  inversions 1. `would_hold_without_float_tolerance` false for both.
- Post-hoc, 44 seen-service pairs: MiniLM 0.7760, 0.7503, 0.7018, 0.7001, 0.7184, p = 0.0027,
  rho = -0.7. BGE 0.8789, 0.8523, 0.8298, 0.8223, 0.8335, p = 9.45e-05, rho = -0.7.
- Post-hoc calibration, same-slot paraphrases below cosine 0.8: MiniLM 67/160 (v1), 111/160 (v5);
  BGE 9/160 (v1), 42/160 (v5).
- Exploratory: 75 matched instances, 55 distinct names.
- Models: `all-MiniLM-L6-v2` @ `1110a243`, `bge-base-en-v1.5` @ `a5beb1e3`. Seed 0. No seed
  spread: deterministic given pinned revisions; axes are 2 encoders x 5 variants.

## Deviations from plan
- H2 was implemented on all 160 test pairs, though an earlier Change log entry had restricted it
  to seen-service slots for ADR-004 alignment. The replacement H2 did not restate a population
  and I widened it without flagging. Resolved by the dated amendment; the diagnostic is recorded.
- Condition (b) is evaluated as `rho <= -0.9 + 1e-9`. Committed pre-run with a test.
- Audit re-run once to record rho at full precision. Means and verdicts identical.

## Assumptions I made
- Pairing key: original `service_name` with the variant-index suffix stripped, plus slot
  position. SGD-X renames every service (`Alarm_1` -> `Alarm_11`).
- Deleted the 619 MB dataset clone after copying the 18 schema files.
- Run-id format `YYYYMMDDTHHMMSSZ-<git-short-sha>`.
- `.gitignore` exceptions for `sanity_check.json` and `per_slot.jsonl`.
- No instruction prefix for either encoder, on the grounds that the task is symmetric.
- N2 singularization is rule-based with an explicit exception list; secondary only.
- Filled `<date>` placeholders in transcribed text with 2026-10-01.

## Things that look wrong or weak
- H2's condition (b) holds only through the float tolerance; a bare comparison fails under both
  encoders. The verdict sits on one adjacent inversion.
- H2 measured cosine to each slot's own test original. ADR-004 defines the covariate against the
  nearest train field, which was not measured. ADR-005 generalizes to that untested relation.
- H1's cutoff is below the cosine of a same-slot paraphrase under MiniLM (41.9% at v1).
- The 160 slots are treated as independent; they are nested in 21 services.
- No interval was pre-registered on any deciding number.
- Encoder contamination is unaddressed: SGD public since 2019, SGD-X since 2021.
- Commit `7fc8825` bundled a CLAUDE.md rule change with a threshold a verdict depends on.

## Decisions needed (human)
- D5: accept / modify / reject ADR-005.
- Whether H2's "Decision informed" line should be narrowed, since it names the
  nearest-train-field covariate that was not measured.
- Whether H1 is worth re-registering with a calibrated cutoff. ADR-005 as drafted forbids its
  current form, so this would be a new experiment, not an edit.
- Whether PR #1 comes out of draft.

## Proposed next step
Define EXP-003, construction of L2 items by holding fields out of train, which the Decision
requires ("L2 items will be constructed") and which SGD test-only services can no longer supply.
Needs `/new-experiment` and the interview; I have not created the record.
