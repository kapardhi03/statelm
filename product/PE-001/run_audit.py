"""PE-001 dataset audit. Runs on Kapardhi's machine; only aggregates leave it.

    uv run python run_audit.py --print-columns --csv /path/to/export.csv
    uv run python run_audit.py --csv /path/to/export.csv --columns columns.yaml
    uv run python run_audit.py --csv ... --columns ... --recheck-sample-out /local/path.csv

Reads a CSV export of the labelling sheet, computes PE-001's measurements A to G, evaluates the
four pre-registered Gate 1 conditions, and writes `runs/PE-001/<run-id>/{config,metrics}.json`.

What is written: counts, ratios, distributions, verdicts. What is never written: a user message, a
reply, or any per-item label value. `safety.assert_output_safe` checks that before the file is
created, and a test feeds the audit fabricated data containing a sentinel string and asserts the
sentinel reaches neither file.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from audit import (
    Item,
    action_distribution,
    completeness,
    corpus_shape,
    duplicates_and_overlap,
    gate_one,
    memory_dependence,
    prompt_lengths,
    reply_templating,
)
from columns import Columns
from normalize import normalize_message
from provenance import (
    SCRIPT_VERSION,
    git_state,
    run_id,
    sha256_file,
    utc_now,
    write_json,
)
from safety import assert_output_safe
from thresholds import (
    CHARS_PER_TOKEN_ESTIMATE,
    MAX_CLASS_CARDINALITY_SHARE,
    MAX_CLASS_NAME_CHARS,
    MAX_CROSS_SPLIT_DUPLICATES,
    MAX_PILOT_OVERLAP,
    MIN_CLASS_N,
    MIN_MEMORY_DEPENDENT,
    RECHECK_SAMPLE_N,
    REQUIRED_LABELER_COVERAGE,
)

REPO = Path(__file__).resolve().parents[2]


def read_header(csv_path: Path) -> list[str]:
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        return next(csv.reader(fh), [])


def read_items(csv_path: Path, cols: Columns, split_by_item: dict[str, str] | None) -> list[Item]:
    items: list[Item] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols.validate_against(list(reader.fieldnames or []))
        for row_no, row in enumerate(reader, start=2):  # 1 is the header
            def get(field: str) -> str:
                name = getattr(cols, field)
                return (row.get(name) or "").strip() if name else ""

            turn_raw = get("turn_index")
            try:
                turn = int(turn_raw) if turn_raw else None
            except ValueError:
                turn = None

            item_id = get("item_id") or f"row-{row_no}"
            items.append(
                Item(
                    row=row_no,
                    item_id=item_id,
                    conversation_id=get("conversation_id"),
                    turn_index=turn,
                    user_message=get("user_message"),
                    action=get("action"),
                    reply=get("reply"),
                    labeler=get("labeler"),
                    split=(split_by_item or {}).get(item_id),
                )
            )
    return items


def load_pilot_ids(path: Path | None) -> set[str] | None:
    """EXP-000's sampled item ids, from its gitignored local manifest.

    Returns None when no manifest is given, which makes Gate 1 condition 3 read NOT_ESTABLISHED
    rather than silently pass. `data-and-splits.md` forbids EXP-000's pilot items in a final test
    split, and EXP-000 sampled from this same deployment, so an unchecked zero would be a guess.
    """
    if path is None:
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    ids: set[str] = set()
    if isinstance(payload, dict):
        for key in ("items", "rows", "sample"):
            entries = payload.get(key)
            if isinstance(entries, list):
                for e in entries:
                    if isinstance(e, dict):
                        for id_key in ("item_id", "id", "conversation_id"):
                            if e.get(id_key):
                                ids.add(str(e[id_key]))
    elif isinstance(payload, list):
        for e in payload:
            if isinstance(e, dict) and e.get("item_id"):
                ids.add(str(e["item_id"]))
    if not ids:
        raise ValueError(
            f"{path}: no item ids found. Expected a mapping with an 'items' list whose entries "
            "carry item_id / id / conversation_id, or a list of such entries."
        )
    return ids


def write_recheck_sample(items: list[Item], out: Path, seed: int) -> int:
    """Write the context-stripped re-label sheet for PE-001's measurement D(2).

    Local output, never under `runs/`: it holds user messages, which is client text. One row per
    sampled item, the message alone with no conversation context and no prior turns, and **no
    action column pre-filled** — pre-filling it would be pre-labelling, which CLAUDE.md rule 3
    forbids outright. The original labels stay in the sheet and are compared afterwards.
    """
    import random

    rng = random.Random(seed)
    eligible = [i for i in items if i.user_message.strip() and i.action.strip()]
    chosen = rng.sample(eligible, min(RECHECK_SAMPLE_N, len(eligible)))
    chosen.sort(key=lambda i: rng.random())  # presentation order, also seeded
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["recheck_id", "user_message", "action_without_context"])
        for n, it in enumerate(chosen, start=1):
            w.writerow([f"rc-{n:03d}", it.user_message, ""])
    # The mapping from recheck_id back to item_id is what makes the comparison possible, and it
    # must not be visible while re-labelling. Separate file, same local directory.
    key = out.with_name(out.stem + ".key.csv")
    with key.open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["recheck_id", "item_id", "original_action"])
        for n, it in enumerate(chosen, start=1):
            w.writerow([f"rc-{n:03d}", it.item_id, it.action])
    return len(chosen)


def build_metrics(items: list[Item], pilot_ids: set[str] | None, split_written: bool) -> dict[str, Any]:
    shape = corpus_shape(items)
    dist = action_distribution(items)
    templ = reply_templating(items)
    mem = memory_dependence(items)
    dupes = duplicates_and_overlap(items, pilot_item_ids=pilot_ids, split_written=split_written)
    comp = completeness(items)
    lengths = prompt_lengths(items)
    return {
        "experiment": "PE-001",
        "A_corpus_shape": shape,
        "B_action_distribution": dist,
        "C_reply_templating": templ,
        "D_memory_dependence_lower_bound": mem,
        "E_duplicates_and_pilot_overlap": dupes,
        "F_label_completeness": comp,
        "G_prompt_length": lengths,
        "gate_1": gate_one(dist=dist, memory=mem, dupes=dupes, comp=comp),
    }


def summarise(metrics: dict[str, Any]) -> str:
    """A terminal summary. Counts and verdicts only, like the file."""
    a, b, c = metrics["A_corpus_shape"], metrics["B_action_distribution"], metrics["C_reply_templating"]
    d, g = metrics["D_memory_dependence_lower_bound"], metrics["G_prompt_length"]
    gate = metrics["gate_1"]
    lines = [
        "PE-001 dataset audit",
        f"  rows {a['rows']}  conversations {a['conversations']}  "
        f"labelled {a['labelled_items']}  unlabelled {a['unlabelled_items']}",
        f"  mean items per conversation {a['mean_cluster_size']}",
        f"  action classes {b['distinct_actions']}  below floor({MIN_CLASS_N}) "
        f"{b['n_classes_below_floor']}  majority share {b['majority_share']}",
        f"  reply templating ratio (normalised) {c['templating_ratio_normalised']}  "
        f"on {c['replies_present']} replies",
        f"  memory-dependent items (LOWER BOUND) {d['items_in_ambiguous_groups']}"
        f"  from {d['repeated_message_groups']} repeated-message groups",
        f"  prompt tokens, ESTIMATED at {g['chars_per_token_divisor']} chars/token: "
        f"median {g['prompt_tokens_estimated']['median']}  max {g['prompt_tokens_estimated']['max']}",
        f"  GATE 1: {gate['overall']}",
    ]
    for name, cond in gate["conditions"].items():
        lines.append(f"    {cond['verdict']:<16} {name}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PE-001 dataset audit (aggregates only)")
    ap.add_argument("--csv", type=Path, required=True, help="CSV export of the labelling sheet")
    ap.add_argument("--columns", type=Path, help="columns.yaml mapping logical fields to headers")
    ap.add_argument("--print-columns", action="store_true", help="print the export's headers and exit")
    ap.add_argument("--exp000-manifest", type=Path, help="EXP-000's local sampler manifest")
    ap.add_argument("--split-assignment", type=Path, help="JSON item_id -> split, once one exists")
    ap.add_argument("--recheck-sample-out", type=Path, help="write the context-stripped re-label sheet here (local path, never under runs/)")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--runs-dir", type=Path, default=REPO / "runs" / "PE-001")
    args = ap.parse_args(argv)

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2

    if args.print_columns:
        # Header names are not client text. No row is read.
        for name in read_header(args.csv):
            print(name)
        return 0

    if not args.columns:
        print("error: --columns is required (or use --print-columns first)", file=sys.stderr)
        return 2

    cols = Columns.load(args.columns)
    split_by_item: dict[str, str] | None = None
    if args.split_assignment:
        split_by_item = {
            str(k): str(v) for k, v in json.loads(args.split_assignment.read_text()).items()
        }
    items = read_items(args.csv, cols, split_by_item)
    if not items:
        print("error: the export has no data rows", file=sys.stderr)
        return 2

    pilot_ids = load_pilot_ids(args.exp000_manifest)
    metrics = build_metrics(items, pilot_ids, split_written=split_by_item is not None)

    rid = run_id(REPO)
    out_dir = args.runs_dir / rid
    config: dict[str, Any] = {
        "experiment": "PE-001",
        "run_id": rid,
        "generated_at": utc_now(),
        "script_version": SCRIPT_VERSION,
        **git_state(REPO),
        "seed": args.seed,
        "input_sha256": sha256_file(args.csv),
        "input_rows": len(items),
        "columns_sha256": cols.sha256(),
        "columns_mapped": sorted(cols.present()),
        "turn_order_from": "turn_index" if cols.turn_index else "export_row_order",
        "exp000_manifest_supplied": args.exp000_manifest is not None,
        "split_assignment_supplied": split_by_item is not None,
        "thresholds": {
            "MIN_CLASS_N": MIN_CLASS_N,
            "MIN_MEMORY_DEPENDENT": MIN_MEMORY_DEPENDENT,
            "MAX_CROSS_SPLIT_DUPLICATES": MAX_CROSS_SPLIT_DUPLICATES,
            "MAX_PILOT_OVERLAP": MAX_PILOT_OVERLAP,
            "REQUIRED_LABELER_COVERAGE": REQUIRED_LABELER_COVERAGE,
            "RECHECK_SAMPLE_N": RECHECK_SAMPLE_N,
            "CHARS_PER_TOKEN_ESTIMATE": CHARS_PER_TOKEN_ESTIMATE,
            "MAX_CLASS_NAME_CHARS": MAX_CLASS_NAME_CHARS,
            "MAX_CLASS_CARDINALITY_SHARE": MAX_CLASS_CARDINALITY_SHARE,
        },
    }

    # The boundary. Both files are checked before either is created, so a guard failure writes
    # nothing rather than leaving one file behind.
    assert_output_safe(metrics, "$metrics")
    assert_output_safe(config, "$config")

    write_json(out_dir / "metrics.json", metrics)
    write_json(out_dir / "config.json", config)
    print(summarise(metrics))
    print(f"\nwrote {out_dir / 'metrics.json'}\nwrote {out_dir / 'config.json'}")

    if args.recheck_sample_out:
        n = write_recheck_sample(items, args.recheck_sample_out, args.seed)
        print(
            f"\nwrote {args.recheck_sample_out} ({n} items, context stripped, action column empty)"
            f"\nwrote {args.recheck_sample_out.with_name(args.recheck_sample_out.stem + '.key.csv')}"
            "\nBoth hold client text. Keep them local; do not commit them."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
