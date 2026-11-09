# PE-003: LoRA fine-tune — does it beat eight examples in a prompt?

Status: **Planned** (code written; nothing has been run)
Owner: Kapardhi
Created: 2026-11-09
Product decision informed: whether to ship a fine-tuned model, or stay with the best prompted rung.
Blocked by: **PE-002's Gate 2, both conditions passing**, and **approval of the Metric below before
any code** (CLAUDE.md rule 1). Gate 2 condition 2 needs the label-noise ceiling, which needs
PE-001's full-context re-test, which needs a week between labelling passes. PE-003 is therefore at
least a week out, and that is the critical path rather than anything in this record.

> **What is his and what is not, as of 2026-11-09.**
> **His:** everything transcribed in the plan's §0 — the label space (Q1a), that he labelled it
> himself with no model involved (Q1b), no written guideline (Q1c), the Google Sheet (Q1d), the
> product-track scope (Q12), the separate series (Q16), ~9B as the primary model (Q5), and PE-002's
> approved Metric, which already fixed **B3 as the rung a fine-tune must beat** before any
> fine-tune existed.
> **Approved by Kapardhi, 2026-11-09:** "approved, write the code". The Hypothesis, Metric and
> thresholds below are now pre-registered and do not move after a result is seen (rule 2). The code
> was written after that approval, at `product/PE-003/`, and **is still not approved to run**: three
> gates refuse in code — PE-002's Gate 2 on both conditions, the Q9 consent record, and the prompt
> freeze on the test split. The Decision section is left for him (rule 5).
> Everything marked *Flagged* is Claude Code's reading rather than his instruction.

---

## The one number that frames this experiment

The split is pre-registered as 200 test / 100 dev / **remainder** train. On a corpus of the size his
">400 examples" suggests, the remainder is small. A dry run of the real split writer on a 367-item
fabricated corpus of the same shape gave **train 64 / dev 102 / test 201**.

So, stated plainly before anything else in this record:

> **The fine-tune will have roughly 64 training examples. B3, the rung it must beat, has 8 of those
> same examples in its prompt. The contest is 64 against 8, not 400 against 8.**

*Flagged by Claude Code, and it is the central risk:* at that size this is a test of whether
supervised fine-tuning changes behaviour **at all** on this data, not a test of what a fine-tune can
do. A null result would be a finding about **data volume**, not about LoRA, and the honest next step
would be the plan's step 4 (grow the data), not a bigger model or a longer sweep. PE-001's audit
reports the real train-split size as its first output; if it comes in materially below ~60, this
record's Hypothesis should be reconsidered before it is approved rather than after it is refuted.

---

## Hypothesis

A LoRA fine-tune of `Qwen/Qwen3.5-9B` on the train split beats **B3** — the same model, same prompt,
eight in-context examples — by at least **10 pp** on `action` accuracy on the frozen test split,
paired per item, at p < 0.05.

**Refuted** if the difference is below 10 pp or not significant. A refutation is not a verdict on
LoRA: at ~64 training examples it is a verdict on this corpus's size, and it routes to the plan's
step 4.

**Reported as UNSTABLE, with no claim either way**, if the three seeds do not agree on the verdict.
Seed spread that can flip the answer means the spread has swamped the effect, and neither a pass nor
a fail should be read from it.

## Setup

### What is being compared

| | The fine-tune | B3 |
|---|---|---|
| Model | `Qwen/Qwen3.5-9B` + LoRA adapter | `Qwen/Qwen3.5-9B`, unmodified |
| Examples | ~64, in the weights | 8, in the prompt |
| Prompt | **B1's template**, unchanged | B1's template + the 8-shot block |

The prompt is deliberately identical to B1's, so the only difference from B3 is **weights versus
examples**. A fine-tune given a shorter prompt would be a different system and the comparison would
no longer isolate anything.

### The recipe, fixed before running

Tinker trains LoRA only and exposes **`rank`**; target modules are not configurable, and its LoRA
primer settles that question anyway ("LoRA performs better when applied to all weight matrices…
attention-only LoRA underperforms even when we match the number of trainable parameters").

| Hyperparameter | Value | Why this, fixed now |
|---|---|---|
| `rank` | **32** (Tinker's default), **not swept** | At a 64-item train split, rank 32 carries about **10,100×** the capacity Tinker's own sizing rule asks for, and even rank 1 carries ~316×. Rank is not the knob for *fitting* this data. Whether it is a knob for *overfitting* it is untested, which is what the dev-set early stopping is for |
| learning rate | **10× the full-fine-tune LR**, from `tinker_cookbook.hyperparam_utils.get_lora_lr_over_full_finetune_lr` | The docs' most emphasised failure mode is porting a full-FT LR to LoRA. The utility returns 10 |
| LR sweep | **3 values**: the utility's figure, and it ×3 and ÷3 | The one hyperparameter the docs call most important. Selected **on dev**, never on test |
| batch size | small (8) | The docs: LoRA is less tolerant of large batches, and raising rank does not fix it |
| epochs | max 10, **early stop on dev `action` accuracy**, patience 2 evaluations | At this n, overfitting is the risk rank is not |
| checkpoint selection | the best **dev** accuracy | Never the best test accuracy. The test split is scored once, on the checkpoint dev chose |
| seeds | **3** | CLAUDE.md requires mean and spread whenever a model is trained |
| checkpoint TTL | set on every save | $0.10/GB/month otherwise, and an untidied adapter store is a running cost for nothing |

**Procedure:** 3 LRs × 3 seeds = 9 runs, each early-stopped on dev. The LR is chosen by **mean dev
accuracy across its three seeds**. Then, and only then, the three checkpoints at that LR are scored
on test, once.

### What is trained on, and the check that catches the silent failure

**Primary configuration: `action` only.** The metric is action accuracy, and a model that must also
emit a reply is a different system. **Secondary, reported and not thresholded: `action` + `reply`**,
which is the shippable shape, with action accuracy measured on it too — so the record says whether
adding the reply objective costs action accuracy. *Flagged:* this is Claude Code's split of a real
tension. What gets measured cleanly and what would get shipped are not the same artifact, and the
secondary run exists so that gap is visible rather than assumed away.

**Loss masking is load-bearing.** Only the completion tokens carry weight 1; every prompt token is
masked to 0. Get it wrong and the model is trained to predict the conversation, the loss curve looks
healthy, and the result is a useless model that nothing in the metrics would flag. So:
**pre-registered check — the number of weight-1 tokens in each training example must equal the
tokenised completion length, asserted per example, and the totals written into the run config.** A
run whose weighted-token count does not match stops rather than trains.

### Where it runs, and what leaves the machine

- **Tinker**, with its training API (`create_lora_training_client`, `forward_backward` with the
  cross-entropy loss, `optim_step`, `save_weights_for_sampler`). *Flagged:* PE-002 deliberately used
  Tinker's documented OpenAI-compatible endpoint for *sampling* rather than guess at SDK signatures.
  Training has no compatible-endpoint equivalent, so PE-003's code must be written against the
  Tinker SDK reference, read at the time, not from memory.
- **This uploads client conversation text**, so the same consent gate PE-002 enforces applies here
  (the plan's **Q9**), with `tinker` named in the record.
- Code entry point: `product/PE-003/`. Written 2026-11-09 after approval: `recipe.py`,
  `dataset.py` (the loss mask and its checks), `trainer.py` (the Tinker adapter and an offline
  stub), `sweep.py`, `run_finetune.py`, and 50 tests — every one against the stub, so no key, no
  network and no credits. Run book in that directory's `README.md`.
- `runs/PE-003/<run-id>/config.json` records: git commit and dirty flag, the split hashes, the prompt
  hash, the base model and Tinker model id, rank, LR, batch size, epochs run, the early-stopping
  decision, the seed, the weighted-token totals, the consent hash, the price table version, and the
  billed token counts.

## Baseline

**B3, pre-registered in PE-002's Metric on 2026-11-09, before this fine-tune existed.** That timing
is the point: a comparison chosen after seeing the fine-tune's numbers can be chosen to flatter it.

Two further comparisons, reported and not thresholded:

- **The label-noise ceiling** from PE-001's re-test, reported as **intra**-rater. It says how much of
  the remaining gap is reachable at all.
- **B4/B5, the frontier rungs**, for the POC sentence: whether the result is "matches a frontier
  model cheaper" or "beats it on our schema". Neither decides whether to ship.

## Metric

**Proposed by Claude Code, 2026-11-09, before any code. Not approved.** Once approved these do not
move after a result is seen; a change and its reason go in the Change log (rule 2).

**Primary metric:** `action` accuracy on the frozen test split — exact match against the vocabulary
after case and whitespace normalisation only, with an out-of-vocabulary answer counting as
**incorrect** and also counted as a parse failure. Identical to PE-002's scoring, deliberately: a
metric that changed between the baseline and the candidate would not be a comparison.

**Primary comparison:** the fine-tune at **seed 0** against B3, paired McNemar on the same items.
Seed 0 is named now, in advance, so the comparison cannot be chosen from among three after the fact.
Seeds 1 and 2 are reported as robustness.

**Deciding interval:** cluster bootstrap by conversation, 10,000 resamples, seeded. Wilson is
reported beside it and is never the headline.

| Outcome | Condition |
|---|---|
| **Supported** | seed 0: difference ≥ **10 pp** and p < **0.05**, **and** all three seeds agree on the verdict |
| **Refuted** | seed 0 below 10 pp or not significant, and all three seeds agree |
| **UNSTABLE** | the three seeds do not agree. No claim either way |

The 10 pp is PE-002's figure and the plan's §3.2's: at a ~200-item test split it is detected about
four times in five, and +5 pp at no reachable size. The all-three-agree rule is a guard against
seed-picking, not a second significance test — requiring all three to pass independently would cost
roughly half the power, which is why it governs *agreement* and not the threshold.

**Reported, not thresholded:** per-class accuracy and the confusion matrix; parse-failure rate;
mean and spread across the three seeds; the dev accuracy curve per run and where early stopping
fired; the LR the sweep chose and the dev means it chose from; cost and latency per item for the
fine-tune against B3 and against B4/B5, which is what the POC sentence rests on; the same fine-tune
on `Qwen/Qwen3.5-4B`, D1's ≤4B curve point; and the `action` + `reply` configuration beside the
`action`-only one. **Nothing about `reply` quality**, per the plan's §3.4, until Q19 gives it a
metric.

## Leakage check

- **Trained on the train split only.** Dev is for early stopping, checkpoint selection and the LR
  sweep. **The test split is scored once**, on the checkpoint dev chose, for the chosen LR.
- **Never select on test.** Not the checkpoint, not the LR, not the configuration. The pre-registered
  procedure fixes each of those on dev before test is touched.
- **B3's eight examples come from the train split**, so the fine-tune and B3 draw on the same
  population and neither has seen dev or test.
- **The prompt is B1's, unchanged and hash-pinned**, the same freeze PE-002 enforces: a test run
  refuses unless the hash matches.
- **`used_in` is extended with `PE-003`** on every item trained or scored, so these items stay
  excludable from the benchmark's validation slice later (**Q17**).
- **Q9 applies.** This uploads client text to Tinker, and the consent gate refuses without a record
  naming that provider.
- *Flagged:* B0's prompt has already seen text from this corpus, because the seller side of these
  conversations was generated by the product SLM. That bears on B0, not on this comparison — the
  fine-tune and B3 both use B1's prompt, which is written against dev.

## Cost

Tinker prices per 1M tokens from `models.json` fetched 2026-11-08; 1,200 prompt + 150 completion
tokens per item assumed until PE-001 measures them.

| Line, at a **64-item** train split | Qwen3.5-9B | Qwen3-8B |
|---|---|---|
| One run, 10 epochs | $1.26 | $0.38 |
| 3 seeds | $3.79 | $1.14 |
| **9-run LR sweep** | **$11.38** | $3.42 |
| Dev evals (102 items × 10 checkpoints × 9 runs) | $4.42 | $2.97 |
| Test pass (201 items × 3 seeds × 2 configurations) | $0.58 | $0.39 |
| Checkpoint storage with a TTL | $0.20 | $0.20 |
| **Whole of PE-003** | **≈ $16.57** | ≈ $7.00 |

If the train split turns out larger, the sweep scales roughly linearly: $26.66 at 150 items,
$53.33 at 300. **Compute is not the constraint at any of those sizes.** The constraint is that 64
examples may simply not be enough to move anything, which is what the Hypothesis is for.

## Result
(pending; nothing has been run)

## Interpretation
(pending)

## Decision
(pending, human; never written by Claude Code)

### Change log
- 2026-11-09: **approved ("approved, write the code") and built.** Status Draft → Planned. 50 tests,
  all offline. The Tinker call shapes were taken from its SDK cheatsheet read the same day, as this
  record committed to, not from memory: `create_lora_training_client(base_model=, rank=)`,
  `forward_backward_async(data=, loss_fn="cross_entropy")`, `optim_step_async(AdamParams(...))`,
  `save_weights_and_get_sampling_client(name=)`, and the `Datum` shape with its one-position shift.
  Three gates refuse in code: PE-002's Gate 2 (every condition row, not the summary line), the Q9
  consent record (naming `tinker` **and** B3's provider), and the prompt freeze on test.

  **Four findings from building it, none of which changes a threshold:**
  1. **A float round-trip would have scored zero seeds.** The sweep selected its learning rate by
     formatting it to a label and parsing it back, so `base_lr × (1/3)` became `3.33e-05` and
     matched none of its own runs: the sweep would have chosen a learning rate and then scored
     **no** seeds on test, returning an empty result rather than failing. Caught by a test;
     learning rates now stay floats and are matched with `isclose`, with a regression test on the
     non-terminating factor.
  2. **A fourth mask check, beyond the one pre-registered here.** The record asked that the number
     of weight-1 positions equal the completion length. A mask with the right *count* in the wrong
     *places* passes that and trains on the conversation anyway, so placement is asserted too.
     Measured on the smoke corpus: 64 weighted positions of 6,034, a 1.06% weighted share, which is
     the shape a classification target should have. A share near 1.0 would mean the mask is idle.
  3. **B3 is run inside PE-003, not imported from PE-002's output.** PE-002's test pass writes
     aggregates only, so there is no per-item correctness on disk to pair against — and that rule is
     right. PE-003 therefore imports PE-002's modules and runs B3 itself, which also makes the
     baseline PE-002's own code rather than a copy that could drift. Its one cost: PE-003's
     constants live in `recipe.py`, because two bare `thresholds` modules cannot both be imported.
     **The promote-to-a-shared-module question EXP-003 raised is now plainly live for this pair, and
     it is still his.**
  4. **The shared output guard needed PE-003's vocabulary**, and one value went into the wrong
     category first: `base_model` is `Qwen/Qwen3.5-9B`, which the strict hash charset rejects and
     the config-identifier charset accepts. The guard caught it rather than a reader noticing later.
     PE-001's 95 and PE-002's 116 tests stay green after the change.

  Still his: whether the Hypothesis survives PE-001's real train-split count, **Q9**, **Q7**, and
  the shared-module question above.
- 2026-11-09: created at Kapardhi's request ("now write PE-003"). Hypothesis, Metric and thresholds
  are Claude Code's proposals awaiting approval; **no code written**. Four things in it are Claude
  Code's and are flagged as such: the **64-against-8 framing**, which is the central risk and is
  stated before anything else rather than in a footnote; the **seed-0-plus-agreement rule**, chosen
  over "all three seeds must pass" because the latter would cost roughly half the power while adding
  no protection the agreement check does not already give; the **action-only primary with an
  action+reply secondary**, which exists so the gap between what is measured cleanly and what would
  be shipped is visible; and the **loss-masking assertion**, because a mis-masked run trains the
  model to predict the conversation, looks healthy in the loss curve, and would not be caught by any
  metric in this record. Open for him: whether the Hypothesis survives PE-001's real train-split
  count, and **Q9** and **Q7** as for PE-002.
