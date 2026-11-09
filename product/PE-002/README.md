# PE-002: baseline ladder — run book

Establishes what a fine-tune has to beat. Two stages, because one of them needs nothing from
anybody.

| Stage | Rungs | Needs | Uploads client text |
|---|---|---|---|
| **1 (built)** | B-triv-maj, B-triv-lex | the split, and nothing else | **No.** No model, no network, no credits |
| **2 (not built)** | B0 – B5 | Q9 consent scope, Q7 frontier revisions, PE-001's Gate 1 | Yes. The first upload in the plan |

Stage 1 is the cheapest possible refutation of this project: if a TF-IDF logistic regression on the
user message matches what the prompted models do, the pattern is lexical, an SLM is not needed, and
no amount of fine-tuning is the right answer. It costs nothing and arrives before any client text
leaves the machine.

## 1. Write the split, once

```sh
cd product/PE-002

# dry run: prints what it would assign, writes nothing
uv run python make_split.py --csv ~/export.csv --columns ../PE-001/columns.yaml

# freeze it
uv run python make_split.py --csv ~/export.csv --columns ../PE-001/columns.yaml \
    --exp000-manifest ~/path/to/EXP-000-annotation/manifest.json --write
```

200 test / 100 dev / remainder train, **assigned by conversation**, pre-registered in the plan's
§3.2. A conversation is never divided across splits, so the item targets are approximate — that is
what stops a duplicated message from straddling a boundary.

**Dry run by default.** `data-and-splits.md`: the test split "is frozen once created. Never
regenerate, filter, or 'clean' it." That makes writing it a one-way door, so `--write` is required
and the script refuses to overwrite an existing assignment.

**Supply `--exp000-manifest` before `--write`.** EXP-000 sampled from this same deployment, and its
pilot items may never enter the final test split. Conversations it drew from are excluded at
*conversation* level, not item level: a sibling turn of a pilot item is the same text one row over.
Without the manifest the script warns loudly and excludes nothing — and the split is then frozen
with that gap in it.

**It refuses rather than degrade.** On a corpus too small for the targets it would otherwise drain
every conversation into test and leave train and dev empty, then freeze that. Two refusals:

- fewer than 300 items → the pre-registered split is unreachable. That is the plan's **Q10**
  (">400 examples" is a recollection, not a count) and a decision for Kapardhi, not something for a
  script to paper over.
- enough items but too few, too large conversations → the targets cannot be met without dividing
  one, which is not allowed. Exit code 4 either way, nothing written.

The assignment lands at `data/product-eval/split_assignment.json`, which is **gitignored and
pinned by a test**, and its SHA-256 goes into every run config. That is the reproducibility record.
It is not committed, unlike the research track's tracked `schema_assignment.json`, because this file
is keyed by conversation and item ids from a WhatsApp export — and in that corpus a conversation id
may well be a phone number. Hashes verify a run; ids are not worth the risk.

## 2. Run stage 1

```sh
# dev, with the per-item file for the scorecard
uv run python run_stage1.py --csv ~/export.csv --columns ../PE-001/columns.yaml \
    --split-assignment ../../data/product-eval/split_assignment.json \
    --split dev --per-item-out ~/local/dev_stage1.jsonl

# test: aggregates only
uv run python run_stage1.py --csv ~/export.csv --columns ../PE-001/columns.yaml \
    --split-assignment ../../data/product-eval/split_assignment.json --split test
```

`--per-item-out` is **refused for the test split**. `data-and-splits.md`: an evaluation script may
read test labels, but a developer "may see only aggregate metrics". The test run emits accuracies,
intervals, the paired discordance counts and the per-class breakdown, and nothing per item.

Output goes to `runs/PE-002/<run-id>/{metrics,config}.json`, both tracked; anything else under a run
directory is gitignored.

## What stage 1 reports, and what it deliberately does not

- **`floor_rung` and `floor_accuracy`** — the better of the two trivial baselines. This is what
  Gate 2 condition 1 compares the prompted rungs against, and the comparison is pre-registered at
  **+10 pp on a paired McNemar at p < 0.05**.
- **`gate_2_condition_1` reads `NOT_ESTABLISHED`** with reason `no_prompted_rung_yet`. Stage 1 has
  nothing to compare, so it reports the floor and leaves the verdict to stage 2. It does not
  pretend to a verdict it cannot reach, in the same way PE-001 handles a missing measurement.
- **The deciding interval is a cluster bootstrap by conversation**, 10,000 resamples, seeded. A
  Wilson interval is reported beside it under a key that says it is not the headline: items are
  `(message, turn)` rows from a few dozen conversations and are not independent, so Wilson is
  systematically too narrow here.
- **`parse_failures` is structurally 0** for both stage-1 baselines, since neither can emit a class
  it did not see in train. It is computed and reported anyway, because stage 2's model rungs can
  emit anything, and the record pre-registers that such an output counts as **incorrect** *and* is
  counted here. A column that is 0 in stage 1 and non-zero in stage 2 is the whole point: it is the
  only number that says whether B2's structured output does any work.
- **Nothing about `reply`.** Per the plan's §3.4, `reply` gets no metric and no claim until PE-001's
  templating ratio says which family applies (Q19).

A **zero-width** cluster interval is not a precision claim: it means every conversation scored
alike, so resampling cannot move the statistic. Treat it as a signal to look at the clusters. A
test pins that behaviour.

## Baselines, and why they are not tuned

`B-triv-maj` predicts the most frequent train `action`, ties broken on the label so the fit is
deterministic. `B-triv-lex` is TF-IDF (word unigrams and bigrams, sublinear term frequency) then
multinomial logistic regression, fitted on **train only**.

Its settings are fixed in code, not tuned. Tuning a baseline on dev and then reporting it as "the
trivial baseline" would overstate the floor, and the floor is exactly what Gate 2 condition 1
measures against. They are recorded in the run config so the choice is auditable.

If train has a single `action` class, the lexical baseline is the majority baseline under another
name, and it is skipped with `degenerate_single_class_train` rather than reported as a second
independent result. If scikit-learn is not installed it is skipped with
`scikit_learn_not_installed`; `B-triv-maj` and the split writer need neither it nor any other
numeric dependency.

## Tests

```sh
uv run python -m pytest tests/ -q
```

65 tests, no model and no network. The statistics carry most of them, because the Gate 2 verdict is
two numbers against a threshold: Wilson checked against the plan's own published figures, the exact
McNemar against a hand-computed value and for symmetry, the cluster bootstrap for determinism,
for being wider than Wilson when clusters differ, for narrowing as clusters are added, and for the
zero-variance case, Holm for monotonicity and the family-size adjustment. Plus the split writer's
invariants (no conversation in two splits, every item assigned, pilot conversations out of test,
determinism, both refusals) and the CLI's two privacy behaviours.

## Files

| File | What it holds |
|---|---|
| `thresholds.py` | Every pre-registered number, each naming where it came from |
| `scoring.py` | Accuracy, Wilson, exact McNemar, the cluster bootstrap, Holm, spread |
| `baselines.py` | B-triv-maj and B-triv-lex, and the parse-failure count |
| `data.py` | Loading the export and applying the frozen split |
| `make_split.py` | The split writer. Dry run by default |
| `run_stage1.py` | The stage 1 CLI |
| `safety.py`, `provenance.py`, `columns.py`, `normalize.py` | Copies of PE-001's. EXP-003's record already put the promote-or-duplicate question to Kapardhi; this is the second reuse, so it is live, and copying is the reversible answer |
