"""PE-002 stage 1: the trivial baselines. Local, no model, no network, no credits.

    uv run python run_stage1.py --csv ~/export.csv --columns columns.yaml \\
        --split-assignment ../../data/product-eval/split_assignment.json --split dev

Establishes the floor that Gate 2 condition 1 compares the prompted rungs against. Stage 1 cannot
evaluate that condition — it has no prompted rung to compare — so it reports the floor and leaves
the condition pending stage 2.

**Per-item output for the dev split only.** `data-and-splits.md`: for test, "you may see only
aggregate metrics". The test run emits accuracies, intervals, the paired discordance counts and the
per-class breakdown, and nothing per item.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from baselines import (
    Prediction,
    fit_majority,
    fit_predict_lexical,
    parse_failures,
    predict_majority,
    to_scored,
    vocabulary_of,
)
from columns import Columns
from data import Item, apply_split, labelled, load_split_assignment, of_split, read_items
from provenance import SCRIPT_VERSION, git_state, run_id, sha256_file, utc_now, write_json
from safety import assert_output_safe
from scoring import (
    accuracy_of,
    cluster_bootstrap,
    paired_compare,
    wilson_interval,
)
from thresholds import ALPHA, BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED, MIN_EFFECT_PP

REPO = Path(__file__).resolve().parents[2]


def per_class(preds: list[Prediction]) -> dict[str, dict[str, int | float]]:
    """Support and accuracy per gold class. Names come from the gold labels, which is the taxonomy.

    PE-001's class-label guard already decided whether this taxonomy is safe to emit as names; if
    its audit withheld them, the same should be done here. Keys are checked by the output guard.
    """
    out: dict[str, dict[str, int | float]] = {}
    for p in preds:
        cell = out.setdefault(p.gold.strip(), {"support": 0, "correct": 0})
        cell["support"] = int(cell["support"]) + 1
        cell["correct"] = int(cell["correct"]) + (1 if p.correct else 0)
    for cell in out.values():
        cell["accuracy"] = round(int(cell["correct"]) / int(cell["support"]), 4)
    return dict(sorted(out.items(), key=lambda kv: (-int(kv[1]["support"]), kv[0])))


def score_rung(preds: list[Prediction], vocabulary: set[str]) -> dict[str, Any]:
    scored = to_scored(preds)
    n = len(scored)
    k = sum(1 for s in scored if s.correct)
    lo, hi = wilson_interval(k, n)
    return {
        "n_items": n,
        "n_correct": k,
        "accuracy": round(accuracy_of(scored), 4),
        # The deciding interval. Conversations are the cluster; resampling items would be too
        # narrow, which is why Wilson sits beside it and never in front of it.
        "cluster_bootstrap_95": cluster_bootstrap(
            scored, accuracy_of, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED
        ),
        "wilson_95_not_the_headline": {"lo": round(lo, 4), "hi": round(hi, 4)},
        # Structurally 0 for both stage-1 baselines: neither can emit a class it did not see in
        # train. Reported anyway, because stage 2's rungs can emit anything and the record
        # pre-registers that such an output counts as incorrect AND is counted here.
        "parse_failures": parse_failures(preds, vocabulary),
        "per_class": per_class(preds),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PE-002 stage 1: trivial baselines (local, no model)")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--columns", type=Path, required=True)
    ap.add_argument("--split-assignment", type=Path, required=True)
    ap.add_argument("--split", choices=("dev", "test"), default="dev")
    ap.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--runs-dir", type=Path, default=REPO / "runs" / "PE-002")
    ap.add_argument(
        "--per-item-out",
        type=Path,
        help="dev only: write a per-item JSONL for the scorecard (local path, holds client text)",
    )
    args = ap.parse_args(argv)

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2
    if args.per_item_out and args.split == "test":
        print(
            "error: --per-item-out is refused for the test split.\n"
            "data-and-splits.md: test labels may be read by an evaluation script, but a developer "
            "may see only aggregate metrics. Use --split dev for the scorecard.",
            file=sys.stderr,
        )
        return 2

    cols = Columns.load(args.columns)
    items: list[Item] = apply_split(
        read_items(args.csv, cols), load_split_assignment(args.split_assignment)
    )
    train = labelled(of_split(items, "train"))
    target = labelled(of_split(items, args.split))
    if not train:
        print("error: the split assignment leaves no labelled training items", file=sys.stderr)
        return 2
    if not target:
        print(f"error: no labelled items in the {args.split} split", file=sys.stderr)
        return 2

    vocabulary = vocabulary_of(train)
    majority_label = fit_majority(train)
    maj_preds = predict_majority(majority_label, target)

    rungs: dict[str, Any] = {"B-triv-maj": score_rung(maj_preds, vocabulary)}
    lex_preds: list[Prediction] | None = None
    lex_settings: dict[str, object] | None = None
    lex_error: str | None = None
    try:
        lex_preds, lex_settings = fit_predict_lexical(train, target, seed=args.seed)
        rungs["B-triv-lex"] = score_rung(lex_preds, vocabulary)
    except ImportError:
        lex_error = "scikit_learn_not_installed"
    except ValueError:
        # Raised when train has a single class, in which case the lexical baseline would be the
        # majority baseline under another name. baselines.py explains why that is not reported as a
        # second independent baseline.
        lex_error = "degenerate_single_class_train"

    floor = max(
        (name for name in rungs),
        key=lambda name: (rungs[name]["accuracy"], name),
    )
    comparison: dict[str, Any] | None = None
    if lex_preds is not None:
        comparison = paired_compare(to_scored(maj_preds), to_scored(lex_preds)).as_dict()

    metrics: dict[str, Any] = {
        "experiment": "PE-002",
        "stage": "stage_1",
        "split": args.split,
        "rungs": rungs,
        "lexical_baseline_skipped": lex_error,
        "paired_lex_vs_maj": comparison,
        # What Gate 2 condition 1 will compare the prompted rungs against.
        "floor_rung": floor,
        "floor_accuracy": rungs[floor]["accuracy"],
        "gate_2_condition_1": {
            "verdict": "NOT_ESTABLISHED",
            "reason": "no_prompted_rung_yet",
            "threshold_pp": MIN_EFFECT_PP,
            "alpha": ALPHA,
        },
    }
    assert_output_safe(metrics, "$metrics")

    rid = run_id(REPO)
    out_dir = args.runs_dir / rid
    config: dict[str, Any] = {
        "experiment": "PE-002",
        "run_id": rid,
        "generated_at": utc_now(),
        "script_version": SCRIPT_VERSION,
        **git_state(REPO),
        "step": "stage_1",
        "split": args.split,
        "seed": args.seed,
        "input_sha256": sha256_file(args.csv),
        "split_assignment_sha256": sha256_file(args.split_assignment),
        "columns_sha256": cols.sha256(),
        "n_train_items": len(train),
        "n_eval_items": len(target),
        "bootstrap_resamples": BOOTSTRAP_RESAMPLES,
        "thresholds": {"MIN_EFFECT_PP": MIN_EFFECT_PP, "ALPHA": ALPHA},
        "lexical_settings": lex_settings,
    }
    assert_output_safe(config, "$config")

    write_json(out_dir / "metrics.json", metrics)
    write_json(out_dir / "config.json", config)

    print(f"PE-002 stage 1 — {args.split} split")
    print(f"  train {len(train)} items   {args.split} {len(target)} items")
    for name, r in rungs.items():
        cb = r["cluster_bootstrap_95"]
        print(
            f"  {name:<12} accuracy {r['accuracy']:.4f}  "
            f"cluster 95% [{cb['lo']}, {cb['hi']}]  width {cb.get('width_pp')} pp"
        )
    if lex_error:
        print(f"  B-triv-lex  skipped: {lex_error}")
    if comparison:
        print(
            f"  lex - maj  {comparison['difference_pp']:+.2f} pp   "
            f"discordant {comparison['discordant']}   p {comparison['p_value']}"
        )
    print(f"  FLOOR for Gate 2 condition 1: {floor} at {metrics['floor_accuracy']:.4f}")
    print(f"\nwrote {out_dir / 'metrics.json'}\nwrote {out_dir / 'config.json'}")

    if args.per_item_out and lex_preds is not None:
        args.per_item_out.parent.mkdir(parents=True, exist_ok=True)
        lex_by_id = {p.item_id: p for p in lex_preds}
        with args.per_item_out.open("w", encoding="utf-8") as fh:
            for p in maj_preds:
                fh.write(
                    json.dumps(
                        {
                            "item_id": p.item_id,
                            "conversation_id": p.conversation_id,
                            "gold_action": p.gold,
                            "B-triv-maj": p.predicted,
                            "B-triv-lex": lex_by_id[p.item_id].predicted
                            if p.item_id in lex_by_id
                            else None,
                        }
                    )
                    + "\n"
                )
        print(
            f"\nwrote {args.per_item_out} (dev per-item, for the scorecard)"
            "\nIt holds label values per item. Keep it local; do not commit it."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
