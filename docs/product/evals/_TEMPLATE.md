# PE-NNN: <title>

Status: Draft | Planned | Running | Done | Abandoned
Owner: Kapardhi
Created: YYYY-MM-DD
Product decision informed: <which product decision this result will change>
Blocked by: <question, decision or PE/EXP ID, or "nothing">

> **This is the product track, not the research track.** Created on Kapardhi's answer to Q16,
> 2026-11-08. Its scope is set by his answer to Q12, 2026-11-08: *"it's a product-evaluation set,
> not the benchmark."*
>
> **No result in this series is a benchmark result**, or evidence for H-A, H-B or H-C, or grounds
> for changing an ADR. ADR-001 still governs the benchmark, which is built from constructed
> conversations with real chats as at most a validation slice. `STATE.md`'s Experiments table stays
> research-only, so nothing here appears in it.
>
> **What does carry over unchanged** from `CLAUDE.md`: the metric and threshold are written before
> running and never moved after a result is seen (rule 2); observed behaviour, model output, human
> judgement, gold label and derived state stay distinct, and model output never becomes a gold
> label nor pre-labels data for a human (rule 3); Claude Code fills Result and Interpretation and
> **never** the Decision (rule 5); and a refuted hypothesis is reported with the same care as a
> supported one (rule 6).
>
> The research series says "Decision informed: <which ADR>". A product eval informs no ADR, which
> is why this series exists separately rather than writing "none" into the research record.

## Hypothesis
One falsifiable sentence. What result would prove it wrong?

## Setup
- Data (split, provenance, size, `labeler`):
- What changes vs baseline:
- Where it runs: <his machine / Tinker / this container> — and what leaves it
- Code entry point: `product/PE-NNN/`
- Seeds and versions recorded in `runs/PE-NNN/<run-id>/config.json`

## Baseline
What we compare against, and what the comparison tells us.

## Metric
Primary metric, and the threshold that counts as support / refutation, written BEFORE running.
Say which figures are reported but not thresholded.

## Leakage check
How test data was kept out of training, prompting and prompt iteration. For this series, also: how
these items stay excludable from the benchmark's validation slice later (Q17).

## Result
(filled after running; numbers only, with run IDs)

## Interpretation
(filled after running; what the numbers do and do not show)

## Decision
(filled by Kapardhi after review; never by Claude Code)

### Change log
- YYYY-MM-DD: created.
