---
name: new-experiment
description: Create a new experiment record from the template before any experiment code is written. Use when starting any new experiment, measurement, or comparison.
argument-hint: "[EXP-NNN] [short-title]"
disable-model-invocation: true
---

Create a new experiment record for: $ARGUMENTS

Current experiments:
!`ls docs/research/experiments/ 2>/dev/null || true`

Steps:

1. If no ID was given, use the next free EXP-NNN number from the list above.
2. Copy `docs/research/experiments/_TEMPLATE.md` to
   `docs/research/experiments/EXP-NNN-<kebab-title>.md`.
3. Interview Kapardhi, one question at a time, until these are filled. Do not invent them:
   - Hypothesis (one falsifiable sentence, plus what result would refute it)
   - Decision informed (which ADR or decision changes depending on the result)
   - Baseline (and what the comparison tells us)
   - Metric and threshold, written now, before any code
   - Leakage check
4. Challenge weak answers. Examples:
   - "Better" → better by which metric, against which baseline?
   - "Generalizes" → to which distribution? Which novelty level?
   - No decision informed → ask whether the experiment is worth running at all.
5. Create the empty directory `experiments/EXP-NNN/`.
6. Add the experiment to the Experiments table in `docs/research/STATE.md` with status Planned.
7. Stop. Do not write experiment code in this step.
