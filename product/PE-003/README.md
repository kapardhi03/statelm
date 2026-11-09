# PE-003: LoRA fine-tune — run book

Fine-tunes `Qwen/Qwen3.5-9B` on the train split with Tinker, and compares it against **B3** — the
same model, the same prompt, eight examples in the prompt instead of in the weights.

**What frames this experiment, before anything else:** the split is 200 test / 100 dev /
**remainder** train. On a corpus of the size the export suggests, the remainder is small. A real run
on the smoke corpus gave **train 64 / dev 102**. So the fine-tune gets ~64 examples and B3 has 8 of
them in its prompt: **64 against 8, not 400 against 8.** A null result here is a finding about data
volume, not about LoRA, and routes to the plan's step 4.

## Run it

```sh
cd product/PE-003

# offline first: the whole pipeline, no key, no upload, no credits
uv run python run_finetune.py --csv ~/export.csv --columns ../PE-001/columns.yaml \
    --split-assignment ../../data/product-eval/split_assignment.json \
    --providers ../PE-002/providers.yaml --consent ../PE-002/consent.yaml \
    --split dev --stub

# for real, on dev
uv run python run_finetune.py ... --gate2-metrics ~/runs/PE-002/<id>/metrics.json --split dev

# the one scored test pass, with the prompt pinned
uv run python run_finetune.py ... --split test --prompt-sha <sha>

# the secondary configuration: trained on action + reply, the shippable shape
uv run python run_finetune.py ... --with-reply
```

## Three gates, in code, before anything trains

**PE-002's Gate 2, both conditions.** `--gate2-metrics` takes PE-002's stage-2 **test** metrics and
the run refuses unless `overall` is `PASS` **and** every condition row is `PASS`. The rows decide,
not the summary line. If condition 1 failed, the pattern is lexical and the track ends rather than
fine-tuning. If condition 2 failed, there is no headroom for a fine-tune to occupy. If either is
`NOT_ESTABLISHED`, the measurement it needs has not been made.

**The Q9 consent record.** Training uploads client conversation text to Tinker, so the same gate
PE-002 enforces applies, and the record must name `tinker` **and** whatever provider B3 runs on.

**The prompt freeze.** `--split test` requires `--prompt-sha` matching the template on disk.

`--stub` skips all three, because it uploads nothing: it is for seeing the pipeline work on your
real split before any of the above is in place.

## The loss mask, and why it has four checks

Only the completion tokens carry weight 1; every prompt token is masked to 0. Get it wrong and the
model is trained to predict the conversation, **the loss curve looks healthy, and no metric in this
experiment would catch it.** So `dataset.py` asserts four things per example and stops the run on
any of them:

1. inputs, targets and weights are the same length;
2. that length is `len(sequence) - 1`, which the one-position shift requires;
3. the number of weight-1 positions equals the tokenised completion length — the check PE-003's
   record pre-registered;
4. those positions are at the **end** of the sequence.

(4) is not in the record and is an addition: a mask with the right *count* in the wrong *places*
passes (3) and trains on the conversation anyway.

The totals go into every run config. On the smoke corpus: **64 weighted positions of 6,034 (1.06%)**
— the shape a classification target should have. A `weighted_share` near 1.0 would mean the mask is
not doing its job.

## The procedure, and what is selected where

| Step | Selected on | Never on |
|---|---|---|
| epochs (early stopping, patience 2, max 10) | dev accuracy | test |
| which checkpoint to keep | best **dev** accuracy | best test accuracy |
| the learning rate (3 values) | mean **dev** accuracy across its 3 seeds | test |
| the verdict | the test split, scored **once** | — |

`rank` is **32 and not swept**: at 64 training items it carries about 10,100× the capacity Tinker's
own sizing rule asks for, and even rank 1 carries ~316×. Rank is not the knob for *fitting* this
data; whether it is a knob for *overfitting* it is what the dev-set early stopping is for. The
learning rate starts at 10× the full-fine-tune figure, which is the docs' most emphasised failure
mode when ported wrong.

## The verdict, and `UNSTABLE`

**Seed 0 decides**, named in advance so the comparison cannot be picked from among three after the
fact. Seeds 1 and 2 are reported.

- **PASS** — seed 0 beats B3 by ≥10 pp at p<0.05, and all three seeds agree on the verdict.
- **FAIL** — seed 0 falls short, and all three agree.
- **UNSTABLE** — the three seeds disagree. **No claim either way**: a spread that can flip the
  answer has swamped the effect.

Requiring all three seeds to pass independently was considered and rejected: at ~80% power each,
that would declare a true effect only about half the time, for protection the agreement check
already gives.

## B3 is run here, not imported

PE-002's test pass writes aggregates only — by design, and that rule is right — so its per-item
correctness is not on disk to pair against. PE-003 therefore imports PE-002's modules and runs B3
itself, in this process, pairing internally. That also means the baseline is **PE-002's own code
rather than a copy of it**: a reimplementation that drifted would change the baseline silently.

The cost of that import is one renamed file. PE-001 and PE-002 each call their constants
`thresholds.py`; two bare modules of the same name cannot both be imported, so PE-003's is
`recipe.py`. The promote-to-a-shared-module question EXP-003 raised is plainly live for this pair,
and it is still Kapardhi's.

## Tests

```sh
uv run python -m pytest tests/ -q
```

50 tests, every one against an offline stub backend — no key, no network, no credits. The mask
carries most of them, including a case that builds a mask with the right count in the wrong places
and asserts it is rejected. Also pinned: early stopping on a plateau versus on a decline, that the
kept checkpoint is the best-dev one and not the last, that each sweep run gets a fresh backend (a
run continuing from the previous one's weights would not be an independent seed), that a
non-terminating learning-rate factor still finds its own runs, and each of the three gates refusing.

## Files

| File | What it holds |
|---|---|
| `recipe.py` | Every pre-registered value, each naming where it came from |
| `dataset.py` | Training examples, the loss mask, and its four checks |
| `trainer.py` | The Tinker adapter and the offline stub |
| `sweep.py` | The training loop, early stopping, and the LR sweep |
| `run_finetune.py` | The CLI, the three gates, and the verdict |
