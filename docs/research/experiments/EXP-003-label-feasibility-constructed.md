# EXP-003: Label feasibility on constructed conversations

Status: Draft (not pre-registered)
Owner: Kapardhi
Created: 2026-10-09
Decision informed: ADR-003 (typed abstention), which D4 leaves Proposed "until label feasibility
is measured on constructed data" (Kapardhi, 2026-10-09)
Blocked by: Kapardhi's review of the Hypothesis, the Metric and the threshold; and a second
independent human annotator, of which none is available as of 2026-10-09

> **Draft only. Nothing here is pre-registered and no code may be written for it yet.**
> Requested by Kapardhi, 2026-10-09, verbatim: "Then draft EXP-003 with /new-experiment: label
> feasibility on constructed conversations, at least 10 items per abstention type by
> construction, two independent human annotators, no AI-suggested labels. Draft only. I'll
> review the Hypothesis, Metric and threshold before anything is built."
>
> The four constraints in that instruction are his and are recorded below as given. Everything
> marked **PROPOSED** is Claude Code's draft wording, written to be corrected or replaced. The
> `new-experiment` skill says these are not Claude Code's to invent and that Kapardhi fills them
> by interview; this file exists because he asked for a draft to review, and it stands in for
> the first half of that interview, not for his answers. Non-negotiable rule 1 still holds: no
> experiment code until Hypothesis, Setup, Baseline, Metric and "Decision informed" are his.
> Two deviations from the skill, both deliberate: `experiments/EXP-003/` was **not** created
> (step 5), and the `STATE.md` row reads **Draft** rather than Planned (step 6), because in this
> repository Planned has meant pre-registered and runnable.

## Constraints set by Kapardhi (his, not open for redrafting)
1. **Constructed conversations**, not the real deployment corpus. Per D2 the benchmark is built
   from constructed conversations and real chats are at most a validation slice.
2. **At least 10 items per abstention type by construction** — the sample is built to contain
   them rather than hoped to contain them, which is what EXP-000 could not do: its real subset
   had 0 hedge and 0 correction cue matches across all 286 customer text turns.
3. **Two independent human annotators.**
4. **No AI-suggested labels.**

## Hypothesis
**PROPOSED, Kapardhi to approve or rewrite.** Two independent human annotators, labelling items
drawn from constructed conversations with the ADR-003 taxonomy and the written guideline, reach
Cohen's κ ≥ 0.6 on each of `ABSTAIN:insufficient`, `ABSTAIN:ambiguous` and `ABSTAIN:conflicting`.
Refuted if any one of the three falls below 0.6 on a category with at least 10 items counted as
`n_either`. A category below the floor is reported as not interpretable and refutes nothing.

What this would and would not establish, stated now so the Result cannot be read wider later: it
is feasibility of the *labels on constructed text*. It says nothing about the frequency of
abstention in real conversations, and nothing about whether a model can produce these labels.

## Setup
**PROPOSED except where marked his.**
- Data: items from constructed conversations. How they are constructed is open (Q1); the choice
  changes what the result means, so it belongs in his review and not in a draft.
- Items: one row per (field, turn), with the conversation up to that turn shown as context, as in
  EXP-000. Labels: NO-OP / VALUE(v) / ABSTAIN:insufficient / ABSTAIN:ambiguous /
  ABSTAIN:conflicting / HEDGED, carried over from EXP-000 so the two are comparable if he wants
  them to be.
- Enrichment by construction (his constraint 2): ≥10 items per abstention type, plus NO-OP and
  VALUE items, so that agreement is not measured on an all-abstention sheet. Totals are open (Q5).
- **The intended type used at construction time is a sampling device, not a label.** It is never
  shown to an annotator, never written into a sheet, and never compared against a human label as
  if it were truth. Under CLAUDE.md rule 3 it is neither human judgment nor a gold label: it is
  construction provenance, the same status ADR-004 gives a novelty level.
- Blinding: two sheets holding the same items, each in its own seeded order recorded in the
  sampler's manifest, paired by item id, labelled independently with no discussion until both are
  complete. Annotators are referred to as Annotator A and Annotator B; no personal name appears
  in a sheet, a manifest, a disagreement list or a metrics file.
- No AI-suggested labels (his constraint 4): an annotator sees conversation text, the field and
  the guideline. No model output, no pre-filled cell, no highlighted candidate span, no ordering
  that encodes an expected answer.
- Agreement is computed in inter mode. `experiments/EXP-000/agreement.py` already computes
  per-category κ, the confusion matrix, the cluster bootstrap and the `n_either` floor, and is
  reusable; whether EXP-003 reuses or copies it is an engineering call for after approval.
- Code entry point: `experiments/EXP-003/` — **not created yet**, because this is a draft.
- Seeds and versions recorded in `runs/EXP-003/<run-id>/config.json`, with the construction
  procedure's own hash alongside the prompt template hash.

## Baseline
**PROPOSED.** EXP-000 produced no valid run, so there is no measured baseline for human agreement
in this project and the comparison cannot be against a past number.

Two candidates, both cheap, and the draft proposes running both:
1. **Collapsed binary abstention** — the three types merged into one ABSTAIN class, κ computed on
   {NO-OP, VALUE, ABSTAIN}. What it tells us: whether the three-way split is what loses agreement.
   High binary κ with low typed κ says the taxonomy's granularity is the problem, which is
   precisely the question D4 left open on ADR-003. Low binary κ says something more basic is wrong
   with the guideline or the items.
2. **Construction-intended type vs each annotator separately**, reported as a diagnostic only and
   labelled as such. What it tells us: whether an item built to be ambiguous reads as ambiguous.
   It is not an accuracy measure and the intended type is not a gold label; if this comparison
   risks being read as one, drop it — that is Kapardhi's call (Q2).

## Metric
**PROPOSED, and this is the part the skill is strictest about: it must be fixed before any code,
and changing it after seeing results is forbidden.**
- Primary: Cohen's κ per category, one-vs-rest, for the three abstention types.
- Threshold: support iff all three are ≥ 0.6, using the 1e-9 tolerance already in
  `experiments/EXP-000/thresholds.py`. Refuted if any interpretable one is below 0.6.
- Interpretability floor: a category with `n_either` < 10 is reported as not interpretable, no κ
  is read from it, and it neither supports nor refutes. `MIN_CATEGORY_N = 10`.
- Spread: cluster bootstrap by conversation, since items from one constructed conversation are not
  independent.
- Also reported, not thresholded: overall κ, the full confusion matrix, the HEDGED column, and the
  per-item disagreement list.
- Both 0.6 and the floor of 10 are carried over from EXP-000, where Kapardhi pre-registered them.
  Carrying them over is a proposal, not an inheritance (Q7).

## Leakage check
**PROPOSED.**
- Items here are pilot items. They must not enter the eventual benchmark test split, and the
  construction records must make that exclusion checkable item by item, the same rule EXP-000 set.
- If a model constructs the conversations, its identity and revision are recorded, and no later
  experiment may evaluate that model on these items without the overlap being stated. This is the
  synthetic-data circularity already listed in `knowns-unknowns.md`: the generator, the baseline
  and the judge must not quietly be the same model.
- Guideline and construction prompts are frozen before labelling and hashed into the run config.
  Iterating a prompt against labelled items would contaminate the measurement.
- No real client conversation text is used, quoted, paraphrased from a sample, or given to any
  tool as a seed. `.claude/rules/data-privacy.md` applies unchanged: client text never leaves
  Kapardhi's machine, and `data/raw/` and `data/scrubbed/` stay unreadable to Claude Code. What
  constructed conversations may be built from is Q1, and "adapted from a real conversation" is not
  one of the options.

## Open questions for Kapardhi
These are the answers the `new-experiment` interview needs and a draft cannot supply.

- **Q1. Who or what constructs the conversations?** Hand-written by him; generated by a frontier
  model from a specification; or adapted from a public DST corpus such as SGD. Each carries a
  different risk: hand-written is small and reflects one person's intuitions, model-generated runs
  into the circularity above and tends to produce tidily unambiguous ambiguity, public-corpus
  adaptation inherits that corpus's conventions and contamination.
- **Q2. What status does the construction-intended type have?** The draft treats it as provenance
  only. Keep or drop baseline 2 above accordingly.
- **Q3. Who is the second annotator?** D3's "second annotator identified (Annotator B)" no longer
  holds as of 2026-10-09, and his constraint 3 requires two humans. Without a second human this
  experiment cannot run as drafted; the intra-annotator fallback in EXP-000's closing note is
  weaker and must be reported as intra-annotator, never as inter-annotator.
- **Q4. Does EXP-000's annotation guideline carry over?** It was approved by Annotator A, the
  asymmetry recorded in EXP-000's Known limitations. If A annotates again, the asymmetry comes
  with it.
- **Q5. Item budget.** ≥10 per abstention type is ≥30 abstention items; how many NO-OP and VALUE
  items beside them, and how many constructed conversations do they come from?
- **Q6. Where do constructed conversations live?** They are not client text, so they can be
  tracked in git, which would make the benchmark auditable. Confirm that is intended.
- **Q7. Are 0.6 and the floor of 10 still the numbers?** They are EXP-000's; nothing obliges
  EXP-003 to reuse them.
- **Q8. Which ADR-003 outcome does which result produce?** The draft says a refutation leaves
  ADR-003 Proposed, but what a refutation would change — merge types, redefine them, drop one —
  is his to state before the measurement, so the Decision is not written around the numbers.

## Result
(pending; nothing has been run, and nothing may be run before approval)

## Interpretation
(pending)

## Decision
(pending, human; never written by Claude Code)
