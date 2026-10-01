"""EXP-002 Step 1: the sanity-check gate.

Reproduces the SGD-X exact-name overlap figures before any similarity work happens. Of
names in test schemas for services unseen in train, the SGD-X paper reports that 71% of
intent names and 65% of slot names exactly match train names. The gate passes only if the
slot rate lands in 60-70% and the intent rate in 66-76%, both on (service, slot) instances
with raw (N0) names.

If the gate fails, EXP-002 stops and reports. This script always exits 0 once it has
computed the numbers: a non-zero exit would be indistinguishable from a crash. The verdict
lives in `sanity_check.json` as `gate.pass`, and the Step 2 audit refuses to run unless it
is true.

Usage:
    uv run python run_sanity_check.py --data-root ../../data/raw/sgd/<commit-sha>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from pathlib import Path

import overlap
import schemas
import thresholds

EXPERIMENT = "EXP-002"
STEP = "step-1-gate"
DATASET_REPO = "https://github.com/google-research-datasets/dstc8-schema-guided-dialogue"


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
    ).stdout.strip()


def make_run_id(short_sha: str) -> str:
    return f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{short_sha}"


def rate_block(
    records: list, reference_names: list[str], *, pipeline: str, unit: str
) -> dict:
    """Exact-match rate for one (kind, pipeline, unit) cell, derived from per-item flags."""
    if unit == "instances":
        query = [r.name for r in records]
    elif unit == "unique":
        query = sorted({r.name for r in records})
    else:
        raise ValueError(f"unknown unit {unit!r}")
    flags = overlap.match_flags(query, reference_names, pipeline=pipeline)
    return {
        "unit": unit,
        "pipeline": pipeline,
        "matched": sum(flags),
        "total": len(flags),
        "rate_percent": round(overlap.rate_from_flags(flags), 4),
    }


def evidence(records: list, reference_records: list, *, pipeline: str) -> dict:
    """Per-item matched / unmatched lists for the gate cell, so the rate is auditable."""
    by_normalized: dict[str, set[str]] = {}
    for ref in reference_records:
        by_normalized.setdefault(overlap.normalize(ref.name, pipeline), set()).add(ref.service)
    matched, unmatched = [], []
    for record in records:
        key = overlap.normalize(record.name, pipeline)
        if key in by_normalized:
            matched.append(
                {
                    "service": record.service,
                    "name": record.name,
                    "train_services": sorted(by_normalized[key]),
                }
            )
        else:
            unmatched.append({"service": record.service, "name": record.name})
    return {"matched": matched, "unmatched": unmatched}


def main() -> int:
    parser = argparse.ArgumentParser(description="EXP-002 Step 1 gate")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--out-root", type=Path, default=Path("../../runs/EXP-002"))
    parser.add_argument("--dataset-commit", required=True)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    here = Path(__file__).parent
    data_root = (here / args.data_root).resolve() if not args.data_root.is_absolute() else args.data_root
    out_root = (here / args.out_root).resolve() if not args.out_root.is_absolute() else args.out_root

    git_commit = git_output("rev-parse", "HEAD")
    tree_dirty = bool(git_output("status", "--porcelain"))
    run_id = args.run_id or make_run_id(git_commit[:7])
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    train_path = data_root / "train" / "schema.json"
    test_path = data_root / "test" / "schema.json"
    train = schemas.load_schema(train_path)
    test = schemas.load_schema(test_path)
    seen, unseen = schemas.partition_test_services(train, test)

    train_slots = list(schemas.all_slots(train))
    train_intents = list(schemas.all_intents(train))
    unseen_slots = list(schemas.all_slots(unseen))
    unseen_intents = list(schemas.all_intents(unseen))

    if not unseen_slots or not unseen_intents:
        raise SystemExit("no unseen-service slots or intents found; check --data-root")

    train_slot_names = [s.name for s in train_slots]
    train_intent_names = [i.name for i in train_intents]

    gate_slot = rate_block(unseen_slots, train_slot_names, pipeline="N0", unit="instances")
    gate_intent = rate_block(unseen_intents, train_intent_names, pipeline="N0", unit="instances")
    slot_ok = thresholds.in_band(gate_slot["rate_percent"], thresholds.GATE_SLOT_BAND)
    intent_ok = thresholds.in_band(gate_intent["rate_percent"], thresholds.GATE_INTENT_BAND)
    gate_pass = slot_ok and intent_ok

    secondary = []
    for kind, records, reference in (
        ("slots", unseen_slots, train_slot_names),
        ("intents", unseen_intents, train_intent_names),
    ):
        for pipeline in ("N0", "N1", "N2"):
            for unit in ("instances", "unique"):
                if pipeline == "N0" and unit == "instances":
                    continue  # that cell is the gate itself
                block = rate_block(records, reference, pipeline=pipeline, unit=unit)
                secondary.append({"kind": kind, **block})

    empty_normalized = sorted(
        {
            r.name
            for r in unseen_slots + unseen_intents + train_slots + train_intents
            for p in ("N1", "N2")
            if overlap.normalize(r.name, p) == ""
        }
    )

    config = {
        "experiment": EXPERIMENT,
        "step": STEP,
        "run_id": run_id,
        "git_commit": git_commit,
        "git_tree_dirty": tree_dirty,
        "seed": args.seed,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dataset": {
            "repo_url": DATASET_REPO,
            "commit": args.dataset_commit,
            "files_read": {
                "train/schema.json": schemas.sha256_file(train_path),
                "test/schema.json": schemas.sha256_file(test_path),
            },
        },
        "normalization": {
            "version": overlap.NORMALIZATION_VERSION,
            "pipelines": sorted(overlap.PIPELINES),
            "gate_pipeline": "N0",
            "stopwords": sorted(overlap.STOPWORDS),
            "never_singularized": sorted(overlap.NEVER_SINGULARIZED),
        },
        "embedding_models": None,
        "input_template": thresholds.EMBEDDING_INPUT_TEMPLATE,
        "input_template_hash": hashlib.sha256(
            thresholds.EMBEDDING_INPUT_TEMPLATE.encode("utf-8")
        ).hexdigest(),
        "thresholds": {
            "gate_slot_band_percent": list(thresholds.GATE_SLOT_BAND),
            "gate_intent_band_percent": list(thresholds.GATE_INTENT_BAND),
            "cosine": thresholds.COSINE_THRESHOLD,
            "jaccard": thresholds.JACCARD_THRESHOLD,
            "h1_min_rate_percent": thresholds.H1_MIN_RATE,
            "h2_c1_max_exact_rate_percent": thresholds.H2_C1_MAX_EXACT_RATE,
            "h2_c2_min_retained_percent": thresholds.H2_C2_MIN_RETAINED,
        },
        "notes": [
            "The gate uses no embedding model; input_template and its hash are recorded for "
            "continuity with the Step 2 audit, which does.",
            "The >=3 seeds convention does not apply: nothing is trained or sampled and this "
            "step is deterministic. A seed is recorded anyway.",
        ],
    }

    result = {
        "experiment": EXPERIMENT,
        "step": STEP,
        "run_id": run_id,
        "populations": {
            "train_services": len(train),
            "test_services": len(test),
            "seen_test_services": [s.name for s in seen],
            "unseen_test_services": [s.name for s in unseen],
            "train_slot_instances": len(train_slots),
            "train_intent_instances": len(train_intents),
            "unseen_slot_instances": len(unseen_slots),
            "unseen_intent_instances": len(unseen_intents),
            "unseen_slot_unique_names": len({s.name for s in unseen_slots}),
            "unseen_intent_unique_names": len({i.name for i in unseen_intents}),
        },
        "gate": {
            "pass": gate_pass,
            "slots": {**gate_slot, "band_percent": list(thresholds.GATE_SLOT_BAND), "in_band": slot_ok},
            "intents": {
                **gate_intent,
                "band_percent": list(thresholds.GATE_INTENT_BAND),
                "in_band": intent_ok,
            },
            "reference_figures_percent": {"slots": 65, "intents": 71},
        },
        "secondary_non_gating": secondary,
        "names_normalizing_to_empty": empty_normalized,
        "evidence": {
            "slots_N0_instances": evidence(unseen_slots, train_slots, pipeline="N0"),
            "intents_N0_instances": evidence(unseen_intents, train_intents, pipeline="N0"),
        },
    }

    (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (run_dir / "sanity_check.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    lines = [
        f"{EXPERIMENT} {STEP} run {run_id}",
        f"dataset commit {args.dataset_commit}",
        f"train services {len(train)}, test services {len(test)}, "
        f"unseen {len(unseen)}, seen {len(seen)}",
        f"slots  {gate_slot['matched']}/{gate_slot['total']} = {gate_slot['rate_percent']:.2f}% "
        f"band {thresholds.GATE_SLOT_BAND} in_band={slot_ok}",
        f"intents {gate_intent['matched']}/{gate_intent['total']} = {gate_intent['rate_percent']:.2f}% "
        f"band {thresholds.GATE_INTENT_BAND} in_band={intent_ok}",
        f"GATE: {'PASS' if gate_pass else 'FAIL'}",
    ]
    report = "\n".join(lines)
    (run_dir / "log.txt").write_text(report + "\n", encoding="utf-8")
    print(report)
    print(f"\nwrote {run_dir}/config.json, sanity_check.json, log.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
