# PE-002: Baseline ladder — what does a fine-tune have to beat?

Status: **Draft**
Owner: Kapardhi
Created: 2026-11-09
Product decision informed: whether to fine-tune at all, and which rung PE-003 must beat. This is
Gate 2 of `docs/research/plan-2026-10-10-modelling-track.md` §4.
Blocked by: **approval of the Metric below before any code** (CLAUDE.md rule 1). Then, per stage:
stage 1 needs PE-001's split; stage 2 additionally needs **Q9** (consent scope) and **Q7** (which
frontier revisions), and PE-001's Gate 1.

> **What is his and what is not, as of 2026-11-09.**
> **His, transcribed in the plan's §0:** the label space is `action` + `reply` per user message
> (Q1a); he labelled the items himself with no model involved (Q1b); there is no written label
> guideline (Q1c); the data is in a Google Sheet (Q1d); this is a product-evaluation set and not
> the benchmark (Q12); the product track has its own series (Q16).
> **Not approved:** the Hypothesis, Metric and thresholds below. **Claude Code's proposals**,
> written before any code as rules 1 and 2 require. The Decision section is left for him (rule 5).
> Everything marked *Flagged* is Claude Code's reading rather than his instruction.

---

## The stage split, and why it matters

PE-002 is **two stages**, because one of them needs nothing and the other needs a decision that
cannot be taken back.

| Stage | Rungs | Needs | Uploads client text? |
|---|---|---|---|
| **1. Local** | B-triv | PE-001's split, and nothing else | **No.** No model, no network, no credits |
| **2. Hosted** | B0 – B5 | Q9 (consent scope), Q7 (frontier revisions), PE-001's Gate 1 | **Yes.** First upload in the whole plan |

*Flagged, and it is the reason for splitting them:* **stage 1 is the cheapest possible refutation
of this project and it costs nothing to run.** If a TF-IDF logistic regression on the user message
matches what the prompted models do, the pattern is lexical, an SLM is not needed, and no amount of
fine-tuning is the right answer. Running it first means that finding arrives before any client text
leaves the machine and before a single credit is spent. Stage 2 cannot start until Q9 is settled,
and §3.1 says why: the first upload is not recoverable.

---

## Hypothesis

**Three conditions. The first two are Gate 2; the third is reported and decides the POC sentence,
not whether to proceed.**

1. **The task needs a language model.** The best prompted rung beats the better of the two B-triv
   baselines by at least 10 pp on `action` accuracy, on a paired test at p < 0.05.
   **Refuted** if it does not: the pattern is lexical, and the honest finding is that this task does
   not need an SLM. That ends the track rather than sending it to PE-003.
2. **There is headroom for a fine-tune.** The best prompted Qwen rung sits at least 10 pp **below**
   the label-noise ceiling.
   **Refuted** if the best prompted rung is already within 10 pp of the ceiling: there is nothing
   for a fine-tune to occupy, and the honest claim becomes cost, latency and on-prem, which
   `knowns-unknowns.md` already names as the risk "frontier solves the task cheaply".
   **Not established**, rather than refuted, if no ceiling exists yet, in the same way PE-001
   condition 2 handles a missing measurement.
3. **Reported, not thresholded: the frontier gap.** B4/B5 against the best prompted Qwen rung. A
   large gap means the POC sentence is "matches a frontier model cheaper"; a small one means "beats
   it on our schema" is in reach. Either way the decision to fine-tune rests on 1 and 2.

*Flagged, on condition 2:* comparing model accuracy against an intra-rater agreement figure treats
that figure as a ceiling on achievable accuracy. That holds only if the first-pass labels are the
gold labels and the re-test estimates their reliability, which is the arrangement here but is an
assumption rather than a fact. It is also, per Q1(c), the **only** ceiling available: one annotator,
no written guideline. The number must be reported as **intra**-rater wherever it appears.

## Setup

### The rungs

| Rung | What it is | What it isolates |
|---|---|---|
| **B-triv-maj** | Always predict the majority `action` | The floor. A model below this is worse than a constant |
| **B-triv-lex** | TF-IDF + logistic regression on the user message, trained on the train split | Whether the pattern is lexical. Beats the SLM → no SLM needed |
| **B0** | `Qwen/Qwen3.5-9B`, the prompt the chatbot ships today | Where the product actually is |
| **B1** | Same model + a written prompt: the action vocabulary, the output format, a few rules | How much of the gap is prompt quality |
| **B2** | B1 + structured output, so the action must come from the vocabulary | How much is format compliance |
| **B3** | B1 + k-shot, **examples from the train split only** | **The rung PE-003 must beat.** The real competitor to LoRA at this data size |
| **B4** | A frontier model, same prompt as B1 (Q7 names it and its revision) | Headroom, and the POC comparison |
| **B5** | A second frontier model from another vendor, same prompt (Q7) | So "frontier" is not one vendor's result |

Also run, because it costs almost nothing and answers a question the plan raises: **B1 and B3 on
`Qwen/Qwen3.5-4B`**, the ≤4B point of D1's size curve. Not a rung in the ladder; reported beside it.

### Settings, fixed before running

- **Decoding:** greedy, temperature 0, for every model rung. This is a classification task.
- **Runs per rung: 3.** Providers are not deterministic even at temperature 0, so CLAUDE.md's "mean
  and spread over ≥3 seeds whenever a model is sampled" applies. Report mean and spread; a rung
  whose spread exceeds its distance to a neighbour has not separated from it.
- **Thinking disabled** on the Hybrid models via the renderer, and recorded in the config: a
  thinking and a non-thinking run are not the same system.
- **k for B3:** proposed **k = 8**, examples drawn from train with a fixed seed, order fixed and
  recorded. Few-shot results move with example choice and order, so both are part of the config.
- **One prompt**, shared by B1, B2, B3, B4 and B5 except for what each rung is defined to change.
- **Prompt freezing, enforced in code, not by discipline.** The prompt template is hashed into
  every run config. A `--split test` run requires `--prompt-sha` and refuses to run unless it
  matches the template on disk. Iteration happens on dev; the test split is scored once per rung
  per the pre-registered plan.

### Where it runs, and what leaves the machine

- **Stage 1** runs on his machine. Nothing leaves but aggregates.
- **Stage 2** sends prompts, which contain client conversation text, to Tinker (`Qwen` rungs) and to
  two frontier providers (B4, B5). **That is the first upload in this plan and it is gated on Q9.**
  Named providers go in the run config, as §3.1(a)'s drafted amendment requires.
- **Per-item outputs for the dev split only.** `data-and-splits.md`: for test, "you may see only
  aggregate metrics". So the dev run writes a per-item JSONL and the HTML scorecard; the test run
  writes aggregates, the paired discordance counts (b and c), and nothing per item.
- Code entry point: `product/PE-002/` — **not created yet**; the Metric below is unapproved.
- `runs/PE-002/<run-id>/config.json` records: git commit and dirty flag, the split hashes, the
  prompt template hash, the rung, the model id and revision, the provider, the decoding settings,
  k and the few-shot example ids, the seed, the price table version, and the token counts billed.

## Baseline

Three comparisons, each answering a different question:

1. **B-triv** is the floor, and the comparison that can end the track. What it tells us: whether
   there is a language task here at all.
2. **The label-noise ceiling** from PE-001's full-context re-test, reported as intra-rater. What it
   tells us: whether any headroom exists for PE-003 to occupy. Without it, condition 2 reads
   NOT_ESTABLISHED.
3. **B3** is the rung PE-003 is measured against, pre-registered here so it cannot be chosen later
   to flatter the fine-tune. Comparing a fine-tune to B0 instead would credit it with fixing the
   prompt and the output format.

## Metric

**Proposed by Claude Code, 2026-11-09, before any code. Not approved.** Once approved these do not
move after a result is seen; a change and its reason go in the Change log (rule 2).

**Primary metric: `action` accuracy** — exact match against the class vocabulary after case and
whitespace normalisation only. Nothing else is normalised: mapping a near-miss onto the nearest
class would be scoring generously, and the generosity would differ by rung.

**An output that is not in the vocabulary counts as incorrect, and is also counted separately as a
parse failure.** Both, pre-registered now: accuracy must not be flattered by discarding unparseable
answers, and the parse-failure rate is the number that says whether B2's structured output is doing
any work.

**Deciding interval: cluster bootstrap by conversation**, 10,000 resamples, seeded. Items are
`(message, turn)` rows from a few dozen conversations and are not independent — the plan's §3.2
records this and PE-001 measures the mean cluster size. A Wilson interval is reported beside it and
is never the headline.

**Thresholds:**

| # | Condition | Threshold |
|---|---|---|
| 1 | Best prompted rung − better B-triv, `action` accuracy | ≥ **10 pp**, paired McNemar **p < 0.05** |
| 2 | Label-noise ceiling − best prompted Qwen rung | ≥ **10 pp**. Below it: no headroom, do not fine-tune. No ceiling available: **NOT_ESTABLISHED** |
| 3 | Frontier gap (B4/B5 − best prompted Qwen) | **Reported, not thresholded** |

The 10 pp comes from the plan's §3.2: at a 200-item test split, +10 pp is detected about four times
in five and +5 pp is undetectable at any size this corpus can reach. It is the smallest difference
this track can honestly call a result, so it is also the smallest headroom worth fine-tuning into.

**One primary comparison per condition. Every other pairing between rungs is secondary, reported
with Holm-corrected p-values, and carries no claim.** Seven rungs would otherwise be 21 pairings at
α = 0.05.

**Reported, not thresholded:** per-class accuracy and the confusion matrix; parse-failure rate per
rung; **cost per item** in dollars and **latency per item**, which are what the POC sentence rests
on; the 4B results beside the 9B; the spread across the 3 runs; and `reply` descriptives only —
**no reply metric and no reply claim**, per the plan's §3.4, until PE-001's templating ratio says
which family applies (Q19).

## Leakage check

- **The prompt is written against the dev split and never against test conversations.** Iteration on
  dev, one scored pass per rung on test, and the prompt hash in the config is what makes that
  checkable after the fact rather than a promise.
- **B0 is not a clean zero-shot rung and must not be presented as one.** The seller side of these
  conversations was generated by the product SLM, and B0's prompt is the system that produced it, so
  that prompt has already seen text from the corpus the test split is drawn from. B0 is "the shipped
  system, measured", which is what it is for. Recorded in the plan's §4 on 2026-10-10.
- **B3's few-shot examples come from the train split only**, never dev or test. Their ids go in the
  config so the choice is auditable.
- **B-triv-lex is fitted on train only** and scored on dev and test, like any other rung.
- **No test label is read outside the scorer.** The dev scorecard shows per-item rows; the test
  report does not.
- **Q17, benchmark exclusion:** every item scored here has `used_in` extended with `PE-002`. This is
  the step that iterates prompts against these conversations, which is exactly what would
  contaminate the benchmark's validation slice later.
- `data/product-eval/` is gitignored and pinned by a test, so no export or per-item file can be
  committed.

## Result
(pending; nothing has been run)

## Interpretation
(pending)

## Decision
(pending, human; never written by Claude Code)

### Change log
- 2026-11-09: created at Kapardhi's request ("ok now write PE-002"). The Hypothesis, Metric and
  thresholds are Claude Code's proposals awaiting his approval; no code has been written. Two
  things in it are not from the plan and are flagged as Claude Code's: the **stage split**, which
  lets B-triv run with no upload and no consent question and puts the project's cheapest possible
  refutation first; and the **parse-failure rule**, which keeps accuracy from being flattered by
  discarding unparseable answers. Open for him: **Q7** (which frontier models and revisions are B4
  and B5), **Q9** (consent scope, which gates stage 2 and is not recoverable afterwards), and
  whether k = 8 is right for B3.
