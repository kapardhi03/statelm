# EXP-003: Label feasibility on constructed conversations

Status: Planned
Owner: Kapardhi
Created: 2026-10-09
Decision informed: ADR-003 (typed abstention), which D4 leaves Proposed "until label feasibility
is measured on constructed data" (Kapardhi, 2026-10-09)
Blocked by: Annotator B, not yet recruited. His instruction: "building may proceed, labelling may
not." Nothing in this record may be labelled, and no agreement run exists.

> **What is approved and what is not, as of 2026-10-09.**
> **Approved by Kapardhi:** the Hypothesis, the Metric and the threshold, "as drafted, with Q5 and
> Q8 below added", plus his eight answers transcribed in the next section. These are now
> pre-registered: the threshold does not move after a result is seen, and any change to it is
> recorded here with its reason (non-negotiable rule 2).
> **Not approved:** the generator build plan near the end of this file. It is Claude Code's
> proposal, no code has been written for it, and he asked to see the plan before any is.
> Everything in this record that is Claude Code's reading rather than his is marked as such.

## Kapardhi's answers to the open questions
Transcribed from Kapardhi, 2026-10-09, verbatim, as he gave them. The questions they answer are
the eight this record carried when it was a draft; they are repeated in condensed form only where
an answer would otherwise be unreadable on its own.

> My answers to EXP-003's open questions, dated 2026-10-09.
> Hypothesis, Metric and threshold are approved as drafted, with Q5 and Q8 below added.
>
> Q1. Item specs (field x intended type x scenario) are drawn by a seeded script. A frontier
>     model writes the conversations from the specs. Record the model and revision; it must
>     never be the baseline or judge on these items. I (Annotator A) must not see the intended
>     types before both sheets are complete.
> Q2. The intended type is construction provenance only, never a gold label. Keep baseline 2,
>     renamed "construction check".
> Q3. Annotator B is one outside person, named to me and never in the repo. No AI help. Not yet
>     recruited: building may proceed, labelling may not.
> Q4. EXP-000's guideline carries over unchanged. Fix labels_reference.txt: value is filled
>     for VALUE and HEDGED, as the guideline says.
> Q5. About 40 conversations, one target turn each, 5 fields: about 200 items, with at least
>     15 per abstention type by construction.
> Q6. Conversations are tracked in git. The manifest with intended types stays gitignored
>     until both sheets are complete, then is committed.
> Q7. Keep kappa >= 0.6 and the n_either floor of 10.
> Q8. All three types >= 0.6: accept ADR-003. Binary kappa high but a type below 0.6: merge
>     that type. Binary kappa low: revise the guideline once and rerun. A type not
>     interpretable: construct more items of that type.

And, on the same instruction, transcribed verbatim as his:

> whoever constructs the items cannot be a blind annotator, which is why Q1 keeps me blind to the
> intended types.

*Flagged by Claude Code, on that last point:* the protection is procedural, not technical. He runs
the seeded spec script and the generator on his own machine, so the specs and the manifest exist
where he can read them. What the tooling can enforce is narrower, and the build plan below does
enforce it: intended types are never printed to stdout, never written into a sheet, never written
into a tracked file, and every step after generation runs from the conversations alone. Blindness
beyond that is his own discipline, and this record says so rather than implying the code secures it.

## Constraints set by Kapardhi (his, not open for redrafting)
1. **Constructed conversations**, not the real deployment corpus. Per D2 the benchmark is built
   from constructed conversations and real chats are at most a validation slice.
2. **At least 10 items per abstention type by construction** — raised to **at least 15** by his
   Q5. The sample is built to contain them rather than hoped to contain them, which is what
   EXP-000 could not do: its real corpus produced 0 hedge and 0 correction cue matches across all
   286 customer text turns, and its real subset was the 18 field-mention turns taken whole.
3. **Two independent human annotators.** Annotator B is one outside person, named to him and
   never in this repository, with no AI help (Q3).
4. **No AI-suggested labels.**

## Hypothesis
**Approved by Kapardhi as drafted, 2026-10-09.** Two independent human annotators, labelling items
drawn from constructed conversations with the ADR-003 taxonomy and the written guideline, reach
Cohen's κ ≥ 0.6 on each of `ABSTAIN:insufficient`, `ABSTAIN:ambiguous` and `ABSTAIN:conflicting`.
Refuted if any one of the three falls below 0.6 on a category with at least 10 items counted as
`n_either`. A category below the floor is reported as not interpretable and refutes nothing.

What this would and would not establish, stated now so the Result cannot be read wider later: it
is feasibility of the *labels on constructed text*. It says nothing about the frequency of
abstention in real conversations, and nothing about whether a model can produce these labels.

## Setup
- **Items.** About 40 conversations, one target turn each, 5 fields, about 200 items, at least 15
  per abstention type by construction (Q5). The five fields are the guideline's: `budget`,
  `property_type`, `location_preference`, `timeline`, `decision_maker`. One row per (field, turn),
  with the conversation up to that turn shown as context, as in EXP-000. Labels: NO-OP / VALUE(v) /
  ABSTAIN:insufficient / ABSTAIN:ambiguous / ABSTAIN:conflicting / HEDGED.
  *Flagged by Claude Code, an arithmetic question on these numbers, open below as Q10:* 40
  conversations with one target turn each give 40 designed slots if a turn carries one designed
  abstention field, and three types at ≥15 need 45.
- **Construction.** Item specs (field × intended type × scenario) are drawn by a seeded script; a
  frontier model writes the conversations from the specs; the model name and revision are recorded
  in the run config and that model may never be the baseline or judge on these items (Q1).
- **The intended type is construction provenance only, never a gold label** (Q2). It is never
  shown to an annotator, never written into a sheet, and never treated as truth. Under CLAUDE.md
  rule 3 it is neither human judgment nor a gold label: it has the status ADR-004 gives a novelty
  level, a record of how the item was built.
- **Blinding.** Two sheets holding the same items, each in its own seeded order recorded in the
  manifest, paired by item id, labelled independently with no discussion until both are complete.
  Annotators are Annotator A and Annotator B; no personal name appears in a sheet, a manifest, a
  disagreement list or a metrics file. Kapardhi is Annotator A and must not see the intended types
  before both sheets are complete (Q1).
- **No AI-suggested labels** (constraint 4): an annotator sees conversation text, the field and the
  guideline. No model output, no pre-filled cell, no highlighted candidate span, and no ordering
  that encodes an expected answer.
- **Guideline.** `EXP-000-annotation-guideline.md` carries over unchanged (Q4). Its companion
  instrument did not: `labels_reference.txt` said "Fill 'value' only for VALUE" where the guideline
  says "Fill `value` for VALUE and HEDGED". Fixed on his instruction, with a test that reads both
  files; recorded in EXP-000's Change log, 2026-10-09.
- **Where things live.** Constructed conversations are tracked in git. The manifest carrying the
  intended types stays gitignored until both sheets are complete, then is committed (Q6).
- **Agreement** is computed in inter mode. `experiments/EXP-000/agreement.py` already computes
  per-category κ, the confusion matrix, the cluster bootstrap and the `n_either` floor.
- Code entry point: `experiments/EXP-003/` — **not created yet**; the build plan is unapproved.
- Seeds and versions recorded in `runs/EXP-003/<run-id>/config.json`, with the spec seed, the
  scenario catalogue hash, the generator's model name and revision, and the prompt template hash.

## Baseline
EXP-000 produced no valid run, so there is no measured baseline for human agreement in this
project and the comparison cannot be against a past number. Two comparisons, both kept on his
instruction:

1. **Collapsed binary abstention** — the three types merged into one ABSTAIN class, κ computed on
   {NO-OP, VALUE, ABSTAIN}. What it tells us: whether the three-way split is what loses agreement.
   High binary κ with low typed κ says the taxonomy's granularity is the problem, which is what D4
   left open on ADR-003. Low binary κ says something more basic is wrong with the guideline or the
   items. His Q8 turns both readings into outcomes, so this comparison is now load-bearing.
2. **Construction check** — the construction-intended type against each annotator separately,
   reported as a diagnostic. Renamed from "construction-intended type vs each annotator" on his
   instruction (Q2). It is not an accuracy measure, the intended type is not a gold label, and
   nothing in the Metric below thresholds it. What it tells us: whether an item built to be
   ambiguous reads as ambiguous to a human.
   *Flagged by Claude Code:* the `research-reviewer` pass of 2026-10-09 argued for dropping this
   comparison, on the grounds that even as a diagnostic it installs construction intent as the
   thing human labels are scored against. His Q2 keeps it and scopes it: provenance only, never a
   gold label. The risk it leaves is one of reading rather than of computation — a high
   construction-check number invites the sentence "the humans were right", which is not what it
   measures. Recorded so that sentence cannot be written later without this paragraph being in view.

## Metric
**Approved by Kapardhi as drafted, 2026-10-09, with Q5 and Q8 added.** Fixed before any code, and
not to be changed after a result is seen.

- Primary: Cohen's κ per category, one-vs-rest, for the three abstention types.
- Threshold: support iff all three are ≥ 0.6, using the 1e-9 tolerance in
  `experiments/EXP-000/thresholds.py`. Refuted if any interpretable one is below 0.6 (Q7).
- Interpretability floor: a category with `n_either` < 10 is reported as not interpretable, no κ is
  read from it, and it neither supports nor refutes. `MIN_CATEGORY_N = 10` (Q7).
- Construction floor, from Q5: at least 15 items per abstention type **by construction**, which is
  five above the interpretability floor so that a type stays interpretable even if annotators place
  some of its items elsewhere.
- Spread: cluster bootstrap by conversation, since items from one constructed conversation are not
  independent.
- Also reported, not thresholded: overall κ, the collapsed binary κ (Baseline 1), the full
  confusion matrix, the HEDGED column, the construction check (Baseline 2), and the per-item
  disagreement list.

**What each outcome produces. Transcribed from Kapardhi, 2026-10-09, verbatim (his Q8):**

> All three types >= 0.6: accept ADR-003. Binary kappa high but a type below 0.6: merge
> that type. Binary kappa low: revise the guideline once and rerun. A type not
> interpretable: construct more items of that type.

That mapping is his, written before the measurement, and it is what "Decision informed" means
here. Claude Code does not fill the Decision section whatever the numbers are.
*Flagged by Claude Code:* "binary kappa high" and "binary kappa low" are not given a number. The
three abstention types have 0.6; the binary comparison that routes between "merge that type" and
"revise the guideline once and rerun" does not. Open below as Q11, and worth fixing before the
run rather than after, since the routing is what the threshold protects.

## Leakage check
- Items here are pilot items. They must not enter the eventual benchmark test split, and the
  construction records must make that exclusion checkable item by item, as EXP-000 required.
- The generator's model and revision are recorded, and that model may never be the baseline or
  judge on these items (Q1). This is the synthetic-data circularity in `knowns-unknowns.md`: the
  generator, the baseline and the judge must not quietly be the same model.
- Guideline, scenario catalogue and prompt template are frozen before labelling and hashed into the
  run config. Iterating a prompt against labelled items would contaminate the measurement.
- No real client conversation text is used, quoted, paraphrased from a sample, or given to any tool
  as a seed. `.claude/rules/data-privacy.md` applies unchanged: client text never leaves Kapardhi's
  machine, and `data/raw/` and `data/scrubbed/` stay unreadable to Claude Code. Constructed
  conversations are not client text, which is why Q6 can track them in git.

## Open questions
Q1 to Q8 are answered above. These four are Claude Code's, raised on 2026-10-09, and three of them
want an answer before the generator is built.

- **Q9. D4 makes constructed data decisive for ADR-003; EXP-000 recorded the opposite rule.**
  EXP-000's pre-registered choices say only the real subset's verdict bears on ADR-003, and that
  agreement on model-authored conversations measures guideline usability rather than the taxonomy.
  `knowns-unknowns.md` still lists transfer from model-authored conversations to real ones as
  Unknown. His Q1 answers "a frontier model writes the conversations", and his Q8 says all three
  types at ≥ 0.6 accepts ADR-003. Those two cannot both stand as written. Which holds: has the
  earlier rule been superseded by D2 and D4, or does accepting ADR-003 on constructed data need
  the real-text caveat attached to it? Raised before the run, because it decides what the Result
  is allowed to say, not how the number is computed.
- **Q10. The item arithmetic.** 40 conversations × 1 target turn × 5 fields = 200 items (Q5), but
  three abstention types at ≥ 15 need 45 designed items, and 40 conversations give 40 designed
  slots if each target turn carries one designed abstention field. Two ways out:
  (a) **45 to 48 conversations**, one designed abstention field per turn: 225 to 240 items, 15 or
  16 per type, 45 to 48 bootstrap clusters. Recommended — it keeps each constructed turn about one
  thing, which is also what makes a turn readable.
  (b) **Keep 40 conversations** and let a target turn carry two designed abstention fields. 200
  items as he wrote, but a turn that is simultaneously ambiguous about budget and conflicting about
  timeline is a more contrived turn, and the two items share a cluster.
- **Q11. The binary κ in Q8 has no number** (see the Metric section). Proposed, for him to set or
  replace: "binary κ high" means ≥ 0.6 on the collapsed {NO-OP, VALUE, ABSTAIN} table, the same
  threshold as the typed categories; "low" means below it.
- **Q12. Designed minimums for VALUE and HEDGED.** Q5 fixes minimums for the three abstention
  types only. The guideline's hardest boundary is VALUE / HEDGED / ambiguous, and if VALUE and
  HEDGED items arise only incidentally from the four non-designed fields, their counts are
  uncontrolled and the confusion matrix around that boundary is thin wherever it matters most.
  Proposed: at least 15 designed VALUE items, of which some with approximations ("around 40
  lakhs"), and at least 15 designed HEDGED items. Not a change to the Hypothesis or the threshold,
  which are about the abstention types only.

## Generator build plan
**Claude Code's proposal, 2026-10-09. Not approved, and no code written.** He asked to see the plan
first. Q10 changes step 1's counts and Q12 changes its quotas, so those two answers come before any
code. Nothing here may be built in a way that labels data or lets a model's output become a label.

**Step 1. Scenario catalogue (`experiments/EXP-003/scenarios.yaml`), his to approve.**
A scenario is the construction device that makes an item belong to its intended type, written as a
specification rather than as text: for `ABSTAIN:ambiguous` on `budget`, "a bare number with no unit
anywhere in the context"; for `ABSTAIN:conflicting` on `decision_maker`, "two incompatible claims,
neither withdrawn and neither corrected"; for `ABSTAIN:insufficient` on `timeline`, "the field is
addressed and no value of its type is recoverable". Every scenario instantiates a distinction the
guideline already draws in its section 3, and the catalogue cites the guideline line it comes from.
This file is effectively the operational definition of each abstention type in the data, so it is
his to approve before anything is generated, not Claude Code's to settle.

**Step 2. Seeded spec drawer (`specs.py`).**
Pure Python, no model, no network. Input: the five fields, the scenario catalogue, the per-type
quotas from Q5 and Q12, and a seed. Output: one spec per conversation — conversation id, target
turn index, the designed (field, intended type, scenario) assignment, the distractor fields, and
the seed-derived nonce. Determinism: same seed, same specs, asserted by a test. The drawer knows
nothing about any model.

**Step 3. Prompt template (`prompt.md`), hashed into every run config.**
Takes one spec and asks for a short WhatsApp-style sales conversation ending at the target turn.
It forbids the model from naming or implying a label, from using the taxonomy's words, and from
meta-commentary. It never contains the label vocabulary as an instruction to reproduce.

**Step 4. Generator (`generate.py`), with a stub backend for tests.**
One model call per spec, model name and revision recorded. Structural validation only, never a
label check: turn count and length bounds, roles alternate, the target turn exists at its index,
the designed field is actually addressed in the target turn, no token from
`LABEL_VOCABULARY` appears anywhere, no meta-text, and for a "no unit anywhere" scenario no
currency or unit token in the whole conversation. A generation that fails validation is re-drawn
with a new nonce and the failure is logged with its reason; nothing is silently discarded.
**No model and no cue list ever decides that an item "is" ambiguous.** That is the whole point of
Q2: only the human labels say so, and the intended type is provenance.

**Step 5. Outputs, split by what Kapardhi may see (Q1, Q6).**
Tracked: the conversations, and a run config under `runs/EXP-003/<run-id>/` carrying the git commit,
the spec seed, the catalogue hash, the prompt hash, the model name and revision, and totals only —
conversations, turns, items. Gitignored until both sheets are complete: the manifest with the
specs, the intended types and the per-type counts. stdout prints totals only. This follows EXP-000's
precedent, where the synthetic stratum counts were deliberately kept out of the tracked census.

**Step 6. Sheets.**
EXP-000's sheet writer, label-reference writer and pilot-items writer are needed again, unchanged
in behaviour. Two options, his call: promote them to `src/statelm/annotation.py` and have both
experiments import them — the second reuse, which is the bar CLAUDE.md sets for shared code — or
copy them into `experiments/EXP-003/` and accept the duplication. Either way EXP-000's tests
stay green, and the sheet generator must run from the tracked conversations alone, with no access
to the manifest.

**Step 7. Tests, on fabricated data, no model calls.**
Spec determinism under a seed; quotas met per type; the structural validators reject each malformed
case; no label token in any generated conversation; the tracked outputs carry no intended type;
stdout carries no intended type; the manifest path is gitignored, asserted with `git check-ignore`
as EXP-000 does; the sheet generator works without the manifest present.

**Where this stops.** Generation, validation and sheets. No labelling, no agreement run, no model
evaluated on these items, and no comparison of a model label to a human label. Labelling waits on
Annotator B (Q3).

## Result
(pending; nothing has been run)

## Interpretation
(pending)

## Decision
(pending, human; never written by Claude Code)

### Change log
- 2026-10-09: drafted at Kapardhi's request, with his four constraints recorded as given and the
  Hypothesis, Metric and threshold marked as proposals for his review.
- 2026-10-09: **his answers to Q1 to Q8 transcribed verbatim, and the Hypothesis, Metric and
  threshold approved as drafted "with Q5 and Q8 below added".** Status moves from Draft to Planned:
  the pre-registered part of this record is now his. Added on the same instruction: item counts
  (Q5) and the outcome mapping (Q8) in the Metric section, the rename of Baseline 2 to
  "construction check" (Q2), the construction-and-blindness sentence transcribed as his, and the
  `labels_reference.txt` fix (Q4), which is recorded in EXP-000's Change log because the instrument
  is EXP-000's. Claude Code added Q9 to Q12 as flags, not as part of his instruction, and the
  generator build plan as a proposal awaiting his approval. Nothing has been built.
