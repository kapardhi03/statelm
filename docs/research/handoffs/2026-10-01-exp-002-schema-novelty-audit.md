# Handoff: 2026-10-01 · EXP-002 schema novelty audit on SGD / SGD-X

## Done
- EXP-002 Steps 0-3: record `docs/research/experiments/EXP-002-schema-novelty-audit.md`, code
  `experiments/EXP-002/`, runs `runs/EXP-002/`, 134 tests, two review passes recorded.
- Dataset pinned to `dstc8-schema-guided-dialogue` @ `e852981`; 18 schema files, hashed per run.
- ADR-004 Accepted, ADR-005 Proposed, Decision and amendment transcribed, arXiv:2110.06800v3
  quoted in `literature.md`, ADR-status rule and CLAUDE.md rule 5 refined.

## Results (numbers only)
Models `all-MiniLM-L6-v2` @ `1110a243`, `bge-base-en-v1.5` @ `a5beb1e3`, seed 0, deterministic;
axes are 2 encoders x 5 variants.
- Gate, run `20261001T172749Z-63641d3`, N0, instances: slots 75/116 = 64.66% (band 60-70,
  published 65); intents 20/28 = 71.43% (band 66-76, published 71). Unique names: 57.29%, 70.37%.
- H1, run `20261001T180031Z-746c803`, n=41, space 215, threshold >= 50%: both-model 12.20%
  (5/41). MiniLM 5/41, Wilson 95% [5.3, 25.5]. BGE 17/41 = 41.46%, Wilson 95% [27.8, 56.6].
  Jaccard >= 0.5: 39.02%. Top-1 identity 56.10%, kappa 0.328.
- H2, same run, 160 pairs/variant. MiniLM v1-v5 0.8012, 0.7752, 0.7384, 0.7346, 0.7351,
  p = 5.53e-11, rho -0.8999999999999998, inversions 1. BGE 0.8819, 0.8617, 0.8421, 0.8320,
  0.8359, p = 4.98e-14, rho identical, inversions 1. `would_hold_without_float_tolerance` false.
- Post-hoc, 44 seen-service pairs: MiniLM 0.7760, 0.7503, 0.7018, 0.7001, 0.7184, p = 0.0027,
  rho -0.7. BGE 0.8789, 0.8523, 0.8298, 0.8223, 0.8335, p = 9.45e-05, rho -0.7.
- Post-hoc, same-slot paraphrases below 0.8: MiniLM 67/160 v1, 111/160 v5; BGE 9/160, 42/160.

## Deviations from plan
- H2 was implemented on all 160 test pairs, though an earlier Change log entry restricted it to
  seen-service slots for ADR-004 alignment. The replacement did not restate a population and I
  widened it without flagging. Resolved by the dated amendment; diagnostic recorded.
- Condition (b) evaluated as `rho <= -0.9 + 1e-9`, committed pre-run with a test. Audit re-run
  once to record rho at full precision; means and verdicts identical.

## Assumptions I made
- Pairing key: original `service_name` with the variant-index suffix stripped, plus slot
  position, since SGD-X renames every service (`Alarm_1` -> `Alarm_11`).
- No instruction prefix for either encoder, on the grounds that the task is symmetric.
- Run-id `YYYYMMDDTHHMMSSZ-<sha>`; tracked `sanity_check.json` and `per_slot.jsonl`; deleted the
  619 MB clone after copying; filled `<date>` with 2026-10-01.

## Things that look wrong or weak
- H2's condition (b) holds only through the float tolerance; a bare comparison fails under both
  encoders. The verdict rests on one adjacent inversion.
- H2 measured cosine to each slot's own test original. ADR-004 defines the covariate against the
  nearest train field, not measured here, and ADR-005 generalizes to that untested relation.
- H1's cutoff sits below the cosine of a same-slot paraphrase under MiniLM (41.9% at v1).
- The 160 slots are treated as independent but nest in 21 services; no interval was
  pre-registered; encoder contamination unaddressed (SGD public 2019, SGD-X 2021).
- Commit `7fc8825` bundled a CLAUDE.md rule change with a threshold a verdict depends on.

## Decisions needed (human)
- D5: accept / modify / reject ADR-005.
- Whether H2's "Decision informed" line should be narrowed, since it names the
  nearest-train-field covariate that was not measured.
- Whether to re-register H1 with a calibrated cutoff; ADR-005 forbids its current form, so that
  is a new experiment.
- Whether PR #1 comes out of draft.

## Proposed next step
Define EXP-003, construction of L2 items by holding fields out of train, which the Decision
requires and which SGD test-only services can no longer supply. Needs `/new-experiment`.
