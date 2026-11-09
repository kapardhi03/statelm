# PE-001: Dataset audit — does the labelled corpus contain the pattern?

Status: **Planned**
Owner: Kapardhi
Created: 2026-11-08
Product decision informed: whether to run PE-002 (baseline ladder) and PE-003 (LoRA fine-tune) on
this corpus at all, and under what split. This is Gate 1 of
`docs/research/plan-2026-10-10-modelling-track.md` §4.
Blocked by: nothing. The Metric was approved on 2026-11-09 and the code exists at
`product/PE-001/`. It needs a CSV export of the sheet to run, and `--exp000-manifest` for Gate 1
condition 3 to be evaluable rather than `NOT_ESTABLISHED`.

> **What is approved and what is not, as of 2026-11-08.**
> **His, transcribed in the plan's §0:** the label space is `action` + `reply` per user message
> (Q1a); he labelled the items himself with no model involved (Q1b); the data is in a Google Sheet
> (Q1d); the product track gets this separate series (Q16); this is a product-evaluation set and
> not the benchmark (Q12).
> **Approved by Kapardhi, 2026-11-09**, in answer to this record as it then stood: "approved, write
> the audit script". The Hypothesis, Metric and the four thresholds are now pre-registered and do
> not move after a result is seen (rule 2). The code was written after that approval, not before.
> The Decision section is still left for him (rule 5), and the Result and Interpretation stay empty
> until the audit is run on his machine.
> Everything marked *Flagged* is Claude Code's reading rather than his instruction.

## Hypothesis

The labelled corpus can support a measurable `action`-classification experiment, in that all four
of these hold:

1. every `action` class that will be scored has at least 10 items;
2. at least 30 items are **memory-dependent** — the gold `action` depends on turns before the
   current user message;
3. no item appears on both sides of a split boundary, and no item is one of EXP-000's pilot items;
4. every item destined for dev or test carries a `labeler` value.

**Refuted** if any one of them fails. A failure is not a reason to reach for a bigger model: it
sends the work to step 4 of the plan (grow or repair the data), as §4's Gate 1 says.

*Flagged:* condition 2 is the one that matters most and the one most likely to fail. EXP-000's
census found **0 correction and 0 hedge cue matches across all 286 real customer turns** of this
deployment. If this corpus is that corpus, the prediction is that few items need prior turns — and
then the data cannot teach behaviour over time, however well the training run goes. That is a
finding worth having before any money is spent, which is why it is condition 2 and not a footnote.

## Setup

- **Data.** The labelling Google Sheet (Q1d), exported to CSV. Size unknown until this runs: his
  recollection is ">400 examples" (Q2, 2026-10-10) in a unit not yet established — see Baseline.
  `labeler` = human (Annotator A) for every item he labelled; `generator` = null (Q1b).
- **Where it runs: on his machine.** The keyword baseline and the duplicate check need the user
  message text, so there is no version of this audit that returns anything useful without touching
  client text. It therefore runs where the text already is. **Only `metrics.json` leaves**, which
  is the pattern `.claude/rules/data-privacy.md` sets for EXP-000's tooling. Claude Code does not
  read the sheet (plan §9, Q20).
- **What changes vs baseline:** nothing is trained and no model is called. This step calls no API,
  needs no GPU and spends no Tinker credits.
- Code entry point: `product/PE-001/`. Written 2026-11-09 after approval: `thresholds.py`,
  `normalize.py`, `safety.py`, `columns.py`, `audit.py` (measurements A–G and the gate, pure
  functions), `provenance.py`, `run_audit.py`, and 95 tests. Run book in its `README.md`.
- Seeds and versions recorded in `runs/PE-001/<run-id>/config.json`: git commit, the export's row
  count and column names, a hash of the export, and the script version.

### Measurements

**A. Corpus shape, and the unit of "example".**
Rows, distinct conversations, distinct user messages, labelled vs unlabelled counts, items per
conversation. The last one is not bookkeeping: it is the **design effect** that the plan's §3.2
power figures need, because items from one conversation are not independent and the deciding
interval is a cluster bootstrap by conversation.

**B. `action` class distribution.** Count per class, and the majority-class share. Also settles
Q18 (what the action set is) and whether any class is abstain-like, which settles Q11.

**C. Are `reply` values templated?** Distinct replies against item count, and again after
normalising whitespace, case and digit runs (a crude slot normaliser). Plus the reply length
distribution. Per plan §3.4 this is measured **before** any reply metric is chosen, because a
templated reply set makes `reply` a second classification and dissolves the problem.

**D. Memory dependence, two ways.**

1. **Automatic, a lower bound, no human needed:** the number of items whose user message text
   (normalised) appears elsewhere in the corpus with a **different** gold `action`. What it
   establishes is that the gold action is **not a function of the normalised message alone**.
   *Flagged, two limits, both carried in `metrics.json`'s own fields rather than left to a reader:*
   (a) it is a **lower bound** — it finds anything only where a message repeats, so an
   all-distinct corpus scores 0 and may still be thoroughly context-dependent, and a low number
   does not establish independence; (b) it **conflates context dependence with label noise**, since
   the same message carrying two actions is equally consistent with context mattering and with the
   labels being inconsistent on identical inputs. A diagnostic is reported and thresholds nothing:
   two different actions at the **same** conversation position are harder to explain by context
   than two at different positions.
2. **Confirmation, if the lower bound falls short:** he re-labels a seeded subsample of 30 items
   with all prior turns stripped, blind to his original labels, and the two label sets are
   compared. The disagreement rate is the memory-dependence estimate. This is his time, so it is
   proposed only as the fallback that condition 2 needs when (1) is inconclusive.

   *Added 2026-11-09, on his answer to Q1(c):* there is **no written label guideline**, so a
   **second and separate** re-test is needed, and the tooling now writes both sheets. The
   memory-dependence sheet strips context; the **label-noise** sheet keeps it, because it must show
   the item under the same conditions the original labelling did. The label-noise ceiling belongs
   to PE-002's Gate 2, but its instrument lives here (`--retest-sample-out`). Using one sheet where
   the other belongs would report memory dependence as label noise, and nothing downstream would
   reveal it.

   **And an ordering constraint, which is cheap to honour and expensive to miss:** the full-context
   re-test comes **before** any guideline is written. A guideline derived from the existing labels
   and then used to re-label measures guideline-following rather than how stably the judgement was
   applied, which is the distinction EXP-000 drew when it labelled its synthetic subset "guideline
   usability, not evidence for ADR-003". Re-test first, then write the guideline from the
   disagreements.

**E. Duplicates and pilot overlap.** Near-duplicate user messages across split boundaries, and
overlap against EXP-000's sampled item ids. `.claude/rules/data-and-splits.md`: "Pilot items used
in EXP-000 and EXP-001 must never enter the final test split", and EXP-000 sampled from this same
deployment corpus, so this is a real check rather than a formality.

**F. Label completeness.** Items missing an `action`, a `reply`, or a `labeler`.

**G. Input length distribution.** Tokens per prompt as PE-002 would build it, which decides whether
32K (`Qwen/Qwen3-8B`) or 64K (`Qwen/Qwen3.5-9B`) is needed, and replaces §7's assumed 1,200-token
prompt with a measured figure.

## Baseline

**EXP-000's census of this deployment, as the comparison that establishes whether this is the same
corpus.** From `runs/EXP-000/20261003T163331Z-b860436/census.json` and
`runs/EXP-000/20261005T191447Z-072dbbc/config.json`: 47 conversation files, 623 turns read, 286
customer text turns, 135 eligible targets, 18 field mentions, 54 media placeholders of which 29
voice notes.

What the comparison tells us: which unit ">400 examples" is counted in, and whether the sheet
covers the corpus EXP-000 measured or a different and larger one. ">400 conversations" would mean
roughly eight times the corpus EXP-000 saw, and every downstream number in the plan would need
redrawing. This is the plan's Q10, answered by measurement rather than by recollection.

*Flagged:* this is a reconciliation, not an accuracy measure. Nothing in the Metric thresholds it.

## Metric

**Proposed by Claude Code, 2026-11-08, before any code. Not approved.** Once approved these do not
move after a result is seen; if one must, the change and its reason are recorded in the Change log
(rule 2).

**Thresholded — the four Gate 1 conditions:**

| # | Condition | Threshold |
|---|---|---|
| 1 | Each scored `action` class | n ≥ 10. A class below it is reported with its count and marked **not measurable**, never dropped or silently merged — the handling EXP-000 pre-registered for its interpretability floor |
| 2 | Memory-dependent items | ≥ 30. Established by measurement D(1) alone; if D(1) < 30 the condition reads **not established** rather than refuted, and D(2) decides it. "Not established" blocks PE-003, not PE-002 |
| | *Narrowed 2026-11-09, interpretation only — the threshold of 30 is unchanged* | What D(1) establishes is that the gold action is **not a function of the normalised message alone**. See the Change log: it conflates context dependence with label noise, so D(1) meeting the threshold does not by itself establish context dependence, and D(2) is what separates them |
| 3 | Cross-split duplicates, and EXP-000 pilot overlap in dev or test | exactly 0 of each |
| 4 | Items destined for dev or test with a `labeler` value | 100% |

**Reported, not thresholded:** the corpus-shape figures and the items-per-conversation design
effect (A); the full `action` distribution and majority share (B); the reply templating ratio and
length distribution (C); the memory-dependence lower bound itself (D1); near-duplicate pairs within
a split (E); missing-field counts (F); the prompt length distribution (G); and the reconciliation
against EXP-000's census.

**Not measured here, on purpose:** any model's accuracy. The trivial baselines (majority class,
TF-IDF logistic regression) moved out of this step into PE-002 as rung **B-triv**, because judging
them needs the paired test that PE-002 sets up, and because a gate that depends on the step it
gates is circular. Recorded in the plan's §4, 2026-10-10, after a `research-reviewer` pass.

## Leakage check

- **Nothing is trained and no model is called**, so there is no train/test contamination to create.
- This audit reads items that will later be dev and test, which is sound **only before the split is
  written**. Once the test split is frozen it is not re-run against test labels:
  `data-and-splits.md` allows evaluation scripts to read them while a developer may "see only
  aggregate metrics".
- **Outputs are counts.** No conversation text, no label values per item, no user message in
  `metrics.json` or in anything committed.
- **Q17, benchmark exclusion:** every item this audit reads gets a stable id and `used_in` records
  `PE-001`. ADR-001 keeps real chats out of the benchmark's construction but allows them as a
  validation slice, and the product track will iterate prompts against these items, which would
  contaminate that slice. The `used_in` field plus the one line `data-and-splits.md` still needs
  (his file) is what keeps them excludable.
- `data/product-eval/` is gitignored and pinned by a case in
  `experiments/EXP-000/tests/test_gitignore.py`, added 2026-11-08, so the CSV export and anything
  derived from it cannot be committed.

## Result
(pending; nothing has been run)

## Interpretation
(pending)

## Decision
(pending, human; never written by Claude Code)

### Change log
- 2026-11-09: **Q1(c) answered, transcribed verbatim: "no written guideline, i just labelled based
  on judgement."** Two consequences recorded in the Setup above. First, the label-noise ceiling that
  PE-002's Gate 2 thresholds on has no instrument other than an intra-rater re-test, and that
  re-test needs the item shown **with** its context, which the memory-dependence sheet strips. The
  script now writes both sheets and the run book sets out which measures what. Second, the
  full-context re-test must happen **before** any guideline is written, or it measures
  guideline-following instead of label stability. Claude Code's reading, not his instruction: a
  guideline is worth writing, and the re-test's disagreements are the right material for it.
- 2026-11-09: **Status Draft → Planned**, on his instruction "approved, write the audit script".
  The Hypothesis, Metric and the four thresholds above are now his, pre-registered, and do not move
  after a result is seen. Code written at `product/PE-001/`: 7 modules and 88 tests, no model, no
  network, no GPU. Run book in that directory's `README.md`.
- 2026-11-09, **one narrowing of an interpretation, recorded here because rule 2 requires it, with
  no threshold changed.** While smoke-testing the script on fabricated data the memory-dependence
  count saturated at every item, because the fabricated actions were assigned at random. That
  exposed a flaw in Claude Code's own measure, not in the data: D(1) counts items whose message
  maps to two different actions, which is equally consistent with **context dependence** and with
  **label noise on identical inputs**, and the first version of this record read it as the former.
  What D(1) establishes is therefore narrower — *the gold action is not a function of the
  normalised message alone* — and D(2), the context-stripped re-label, is what separates the two
  readings. **The threshold stays at 30**, both limits now travel in `metrics.json`'s own fields
  (`is_lower_bound`, `establishes`, `conflates`, `measure_has_purchase`), and a same-turn-conflict
  diagnostic is reported and thresholds nothing. Found by Claude Code, 2026-11-09; the change is to
  what the number may be read as, not to what is measured or to any verdict.
- 2026-11-08: created on Kapardhi's answer to Q16 ("yes to Q16"), in the new product series this
  answer approves. The Hypothesis, Metric and thresholds are Claude Code's proposals awaiting his
  approval; his transcribed answers to Q1(a), Q1(b), Q1(d) and Q12 are recorded in the plan's §0
  and are reflected in the Setup and Baseline above. No code written. Q1(c) (whether a written
  label guideline exists) and Q18 (the action set) are open and neither blocks this step; Q1(c)
  blocks Gate 2 in PE-002, because with a single annotator the intra-rater re-test is the only
  route to a label-noise ceiling.
