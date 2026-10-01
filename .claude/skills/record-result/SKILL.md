---
name: record-result
description: Record the outcome of a finished experiment run into its experiment file. Use after an experiment run completes and metrics exist.
argument-hint: "[EXP-NNN] [run-id]"
disable-model-invocation: true
---

Record results for: $ARGUMENTS

Steps:

1. Read the experiment file in `docs/research/experiments/` and the run outputs in
   `runs/<EXP-NNN>/<run-id>/` (`config.json`, `metrics.json`).
2. Compare results against the metric and threshold written BEFORE the run. If the threshold
   was changed after running, say so explicitly in the Result section.
3. Fill **Result** with numbers only: metric values, seeds, spread, run IDs, sample sizes.
4. Fill **Interpretation** with what the numbers do and do not show. Include:
   - whether the hypothesis is supported, refuted, or inconclusive
   - confounds and threats to validity (leakage, small n, prompt sensitivity, contamination)
   - what this result does NOT license us to claim
5. Leave **Decision** empty. Write under it: `(pending human review)`.
6. Run the `research-reviewer` subagent on the experiment file and append its findings under
   a `## Review` heading.
7. Update the experiment's status in `docs/research/STATE.md` to Done (awaiting decision).
