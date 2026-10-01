# EXP-002: schema novelty audit on SGD / SGD-X

Record, hypotheses and every pre-registered threshold:
`docs/research/experiments/EXP-002-schema-novelty-audit.md`. Read that first. This directory
only implements what the record specifies.

## Status

- **Step 0, data acquisition**: done. Schemas copied to `data/raw/sgd/<dataset-commit>/`.
- **Step 1, the gate**: implemented here (`run_sanity_check.py`).
- **Step 2+, H1 and H2**: not implemented yet. They run only if the gate passes.

## Data

Source: `https://github.com/google-research-datasets/dstc8-schema-guided-dialogue`, pinned to
commit `e852981ae34990f4358979625854259302feaa78`. The 18 `schema.json` files (original
train/dev/test plus SGD-X v1-v5) are copied to `data/raw/sgd/<commit>/`, which is gitignored.
Their SHA-256 hashes are recorded in each run's `config.json`. No dialogue files and no state
annotations are read, at any step.

To restore the data in a fresh checkout:

```
git clone --depth 1 https://github.com/google-research-datasets/dstc8-schema-guided-dialogue /tmp/sgd
git -C /tmp/sgd checkout e852981ae34990f4358979625854259302feaa78   # already HEAD at time of writing
cd /tmp/sgd && find . -name schema.json -print0 \
  | xargs -0 -I{} cp --parents {} /path/to/statelm/data/raw/sgd/e852981ae34990f4358979625854259302feaa78/
```

## Running

```
cd experiments/EXP-002
uv run pytest                                    # 46 test functions, 82 cases; no network or data needed
uv run python run_sanity_check.py \
  --data-root ../../data/raw/sgd/e852981ae34990f4358979625854259302feaa78 \
  --dataset-commit e852981ae34990f4358979625854259302feaa78
```

Outputs land in `runs/EXP-002/<run-id>/` with run ids shaped `YYYYMMDDTHHMMSSZ-<git-short-sha>`.

## The gate

Of names in test schemas for services unseen in train, the SGD-X paper reports 71% of intent
names and 65% of slot names exactly matching train names. The gate recomputes both on
`(service, slot)` instances with raw (N0) names, and passes only if slots land in 60-70% and
intents in 66-76%. **If it fails, EXP-002 stops and reports.** H1, H2 and all embedding work
are downstream of it.

`run_sanity_check.py` exits 0 whenever it managed to compute the numbers, including on a
failing gate: a non-zero exit would be indistinguishable from a crash. The verdict is
`gate.pass` in `sanity_check.json`, and the Step 2 audit will refuse to run unless it is true.

## Files

| File | What it holds |
|---|---|
| `thresholds.py` | Every pre-registered number, in one auditable place |
| `overlap.py` | N0 / N1 / N2 normalization, exact match, token Jaccard. Pure functions |
| `schemas.py` | Schema loading, provenance hashing, seen / unseen partition |
| `run_sanity_check.py` | Step 1 gate, writes `config.json`, `sanity_check.json`, `log.txt` |
| `tests/` | Hand-computed expectations for every measure and the gate's end-to-end math |

`N2` normalization is deliberately lossy and rule-based, and it never decides anything: it
appears in secondary reporting only. Its limits are documented on `overlap.singularize` and
pinned by tests.
