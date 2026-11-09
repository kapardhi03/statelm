# PE-001: dataset audit — run book

Reads a CSV export of the labelling sheet, computes the measurements PE-001's record
pre-registered, evaluates the four Gate 1 conditions, and writes aggregates.

**This runs on Kapardhi's machine.** It reads client conversation text, because its duplicate check
and its message-grouping measurements cannot be computed without it. Only `metrics.json` and
`config.json` leave, and `safety.assert_output_safe` checks every value in both before either file
is created: a value is allowed only if it is a number, a bool, null, a short non-reversible hash, or
a string from a closed vocabulary. A test feeds the audit fabricated data carrying a sentinel in
every client-text field and asserts the sentinel reaches neither file nor the terminal.

No model is called. No network access is needed. No GPU, no Tinker credits.

## Run it

```sh
cd product/PE-001

# 1. See the export's headers. Reads the header row only, no data row.
uv run python run_audit.py --print-columns --csv ~/path/to/export.csv

# 2. Copy the example mapping and set each value to the matching header.
cp columns.example.yaml columns.yaml && $EDITOR columns.yaml

# 3. Audit.
uv run python run_audit.py \
    --csv ~/path/to/export.csv \
    --columns columns.yaml

# 4. With the two inputs that Gate 1 condition 3 needs, when you have them.
uv run python run_audit.py \
    --csv ~/path/to/export.csv \
    --columns columns.yaml \
    --exp000-manifest ~/path/to/EXP-000-annotation/manifest.json \
    --split-assignment ~/path/to/split_assignment.json
```

Output lands in `runs/PE-001/<run-id>/`. `metrics.json` and `config.json` are tracked by git; the
root `.gitignore` keeps everything else under a run directory local.

## The two inputs that are not the sheet

**`--exp000-manifest`** is EXP-000's sampler manifest, which holds the item ids it drew.
`.claude/rules/data-and-splits.md` forbids EXP-000's pilot items in a final test split and EXP-000
sampled from this same deployment, so without the manifest the overlap is unknown and **Gate 1
condition 3 reads `NOT_ESTABLISHED` rather than passing**. That is deliberate: an unchecked zero
would be a guess.

**`--split-assignment`** is a JSON map of `item_id -> split`. It does not exist yet, because the
split has not been written. Until it does, the cross-split half of condition 3 reads
`split_not_yet_written`.

## Where the file is in the sheet's terms

`columns.example.yaml` lists the logical fields and says what is lost if an optional one is
missing. Two worth knowing before you run it:

- **no `turn_index`** → turn order falls back to the export's row order, and `config.json` records
  `turn_order_from: export_row_order`, because "earlier in the conversation" is then an assumption
  about the export rather than a fact.
- **no `item_id`** → ids become `row-<n>`, which are stable only while the row order is. The
  pilot-overlap check and the re-label key both get fragile. Worth adding a column.

## Two re-label sheets, and the order they must be done in

They measure different things. Using one where the other belongs reports memory dependence as label
noise, or the reverse, and nothing downstream would reveal the mistake.

| Flag | Shows the item | Measures | Needed by |
|---|---|---|---|
| `--retest-sample-out` | **with** its conversation context, as the original labelling saw it | **label noise**: how stably the same judgement is applied | PE-002's Gate 2, which thresholds on a label-noise ceiling |
| `--recheck-sample-out` | **without** context: the message alone | **memory dependence**: whether the action needed the prior turns | PE-001's Gate 1 condition 2, when the automatic lower bound falls short |

```sh
# full context -> the label-noise ceiling
uv run python run_audit.py --csv ... --columns columns.yaml \
    --retest-sample-out ~/local/retest.csv --seed 11

# context stripped -> memory dependence
uv run python run_audit.py --csv ... --columns columns.yaml \
    --recheck-sample-out ~/local/recheck.csv --seed 0
```

Use **different `--seed` values** if the two measurements should not share a sample; the run says so
out loud when both sheets are written with one seed.

### The sequencing rule, and it is easy to get wrong

Kapardhi's answer of 2026-11-09: there is **no written label guideline** — the labels are judgement
in the moment. Writing one now is worth doing, and it has to come **after** the full-context
re-test, not before.

A guideline written by reading the existing labels, then used to re-label, turns the re-test into a
measure of **guideline-following** rather than of how stably the judgement was applied in the first
place. That is the same distinction EXP-000 drew for its synthetic subset, where agreement on
model-authored conversations was labelled "guideline usability, not evidence for ADR-003". So:

1. **Re-test first**, blind, with no guideline written and the key file closed.
2. **Then** write the guideline, using the disagreements as the material — they are precisely the
   cases where a written rule would have helped.
3. A later re-test *against* the guideline measures something else, and is reported as such.

Both sheets write the label column **empty** and keep the answer key in a separate file. Pre-filling
it would be pre-labelling, which CLAUDE.md rule 3 forbids outright, and a test asserts the column is
empty in both.

## What the context-stripped sheet is for

Gate 1 condition 2 asks whether at least 30 items are memory-dependent. The automatic measure is a
**lower bound** and it **conflates context dependence with label noise** (see below), so when it
falls short the condition reads `NOT_ESTABLISHED` and the context-stripped sheet decides it:
disagreement with the original label, on an item shown without its context, is evidence that the
action depended on something the stripped version does not show.

Both sheets hold client text. Keep them local; `data/product-eval/` is gitignored for this.

## What measurement D does and does not establish

It counts items whose normalised message appears elsewhere with a **different** gold action, so
what it establishes is that **the gold action is not a function of the message alone**. That is
narrower than "the action depends on prior turns", in two ways that `metrics.json` carries in its
own fields:

- `is_lower_bound: true` — it sees only where a message repeats. An all-distinct corpus scores 0
  and may still be thoroughly context-dependent. `measure_has_purchase` says whether any message
  repeated at all.
- `conflates: context_dependence_with_label_noise` — the same message with two actions is equally
  consistent with context mattering and with the labels being inconsistent on identical inputs.
  Found while smoke-testing this script on fabricated data, where the count saturated at every item
  because the fabricated actions were random. The re-label above is what separates them.

`ambiguous_groups_with_same_turn_conflict` is a diagnostic and nothing thresholds it: two different
actions at the **same** conversation position are harder to explain by context than two at
different positions.

## Gate 1 reason codes

Reasons are codes rather than prose so that the output guard can keep a closed vocabulary — if it
admitted free-form strings it would stop being a guard.

| Code | Meaning |
|---|---|
| `classes_below_floor_listed` | At least one action class is under the floor; `B_action_distribution.classes_below_floor` names them |
| `lower_bound_below_floor_recheck_decides` | Measurement D's lower bound is under 30, so condition 2 is not established and the re-label decides it |
| `one_half_unchecked` | Condition 3 could not be evaluated: no EXP-000 manifest, or no split assignment, or neither |

## Tests

```sh
uv run python -m pytest tests/ -q
```

95 tests, no model and no network. They cover every measurement against fabricated data with known
answers, the normalisers the three grouping measurements share, the column mapping, the CLI, the
re-label sheet's seeding and its empty action column, and the output guard — including a negative
control, so the sentinel search can actually fail.

## Files

| File | What it holds |
|---|---|
| `thresholds.py` | The pre-registered thresholds, each naming where it came from |
| `normalize.py` | The text normalisers the grouping measurements share |
| `safety.py` | The output guard and the class-label guard |
| `columns.py` | The logical-field to header mapping |
| `audit.py` | Measurements A to G and the Gate 1 verdict. Pure functions, no I/O |
| `provenance.py` | Run id, git state, input hashes |
| `run_audit.py` | The CLI |
