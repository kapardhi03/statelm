"""Write the frozen split assignment, once.

    uv run python make_split.py --csv ~/export.csv --columns columns.yaml            # dry run
    uv run python make_split.py --csv ... --columns ... --exp000-manifest ... --write

Pre-registered in `docs/research/plan-2026-10-10-modelling-track.md` §3.2 and reproduced in
PE-002's record: **200 test / 100 dev / remainder train, assigned by conversation.**

**Dry run by default.** `data-and-splits.md`: "data/splits/test/ is frozen once created. Never
regenerate, filter, or 'clean' it." That makes writing it a one-way door, so nothing is written
without `--write`, and the dry run prints exactly what would be assigned.

**The assignment file stays local** at `data/product-eval/split_assignment.json`, which is
gitignored and pinned by a test. Its hash goes into every run config instead, which is what makes a
run reproducible. The reason it is not committed, unlike the research track's tracked
`schema_assignment.json`: this file is keyed by conversation and item ids from a WhatsApp export,
and in that corpus a conversation id may well be a phone number. Hashes are enough for
verification; ids are not worth the risk.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

from columns import Columns
from data import Item, read_items
from provenance import SCRIPT_VERSION, git_state, run_id, sha256_file, utc_now, write_json
from thresholds import DEV_ITEMS_TARGET, SPLIT_SEED, TEST_ITEMS_TARGET

REPO = Path(__file__).resolve().parents[2]
DEFAULT_OUT = REPO / "data" / "product-eval" / "split_assignment.json"


def load_pilot_conversations(path: Path | None) -> set[str]:
    """Conversation ids EXP-000 sampled from, which may not enter the test split.

    `data-and-splits.md`: "Pilot items used in EXP-000 and EXP-001 must never enter the final test
    split." Excluded at CONVERSATION level, not item level: a conversation whose other turns were
    pilot items is the same text, so putting its siblings in test would be the same leak one row
    over.
    """
    if path is None:
        return set()
    payload = json.loads(path.read_text(encoding="utf-8"))
    convs: set[str] = set()
    entries = payload.get("items") if isinstance(payload, dict) else payload
    if isinstance(entries, list):
        for e in entries:
            if isinstance(e, dict):
                for key in ("conversation_id", "conv_id", "conversation"):
                    if e.get(key):
                        convs.add(str(e[key]))
    if not convs:
        raise ValueError(
            f"{path}: no conversation ids found. Expected a mapping with an 'items' list whose "
            "entries carry conversation_id."
        )
    return convs


def assign(
    items: list[Item], *, pilot_conversations: set[str], seed: int
) -> tuple[dict[str, str], dict[str, object]]:
    """Assign every item to train, dev or test, by conversation.

    Conversations are shuffled once under the seed, then filled test-first to its item target, then
    dev, then the rest to train. Filling by conversation means the targets are approximate: a
    conversation is never split across two splits, which is what keeps a duplicate message from
    straddling a boundary.

    Conversations EXP-000 sampled from are held out of test and placed in train.
    """
    by_conv: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        by_conv[it.conversation_id].append(it)

    eligible = sorted(c for c in by_conv if c not in pilot_conversations)
    excluded = sorted(c for c in by_conv if c in pilot_conversations)
    rng = random.Random(seed)
    rng.shuffle(eligible)

    # The pre-registered targets assume a corpus of roughly 400 items. If the export is materially
    # smaller they are unreachable, and filling test-first would drain every conversation into test
    # and leave train and dev empty — a split that is useless and, once written, frozen. That is a
    # finding about the corpus (the plan's Q10: ">400 examples" is a recollection, not a count),
    # so it is refused here rather than papered over.
    minimum = TEST_ITEMS_TARGET + DEV_ITEMS_TARGET
    if len(items) <= minimum:
        raise ValueError(
            f"the export has {len(items)} items, but the pre-registered split needs more than "
            f"{minimum} ({TEST_ITEMS_TARGET} test + {DEV_ITEMS_TARGET} dev, with a train split "
            "left over). Either the corpus is smaller than the plan's §3.2 assumed, which is the "
            "plan's Q10 and a decision for Kapardhi, or the export is partial. Nothing written."
        )

    assignment: dict[str, str] = {}
    counts = {"train": 0, "dev": 0, "test": 0}

    def place(conv: str, split: str) -> None:
        for it in by_conv[conv]:
            assignment[it.item_id] = split
        counts[split] += len(by_conv[conv])

    remaining = list(eligible)
    for target_split, target_n in (("test", TEST_ITEMS_TARGET), ("dev", DEV_ITEMS_TARGET)):
        while remaining and counts[target_split] < target_n:
            place(remaining.pop(0), target_split)
    for conv in remaining:
        place(conv, "train")
    for conv in excluded:
        place(conv, "train")

    if counts["train"] == 0 or counts["dev"] < DEV_ITEMS_TARGET or counts["test"] < TEST_ITEMS_TARGET:
        raise ValueError(
            f"the split did not reach its pre-registered targets: {counts} against "
            f"test>={TEST_ITEMS_TARGET}, dev>={DEV_ITEMS_TARGET}, train>0. Conversations are never "
            "divided across splits, so a corpus of few large conversations can fail this even when "
            "the item count looks sufficient. Nothing written."
        )

    report: dict[str, object] = {
        "items": len(items),
        "conversations": len(by_conv),
        "counts": counts,
        "targets": {"test": TEST_ITEMS_TARGET, "dev": DEV_ITEMS_TARGET},
        "pilot_conversations_excluded_from_test": len(excluded),
        "seed": seed,
        "conversations_per_split": {
            s: sum(1 for c in by_conv if assignment[by_conv[c][0].item_id] == s)
            for s in ("train", "dev", "test")
        },
    }
    return assignment, report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Write the frozen split assignment (dry run by default)")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--columns", type=Path, required=True)
    ap.add_argument("--exp000-manifest", type=Path, help="EXP-000's local sampler manifest")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=SPLIT_SEED)
    ap.add_argument("--runs-dir", type=Path, default=REPO / "runs" / "PE-002")
    ap.add_argument("--write", action="store_true", help="actually write it. Frozen once written")
    args = ap.parse_args(argv)

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2
    if args.out.exists() and args.write:
        print(
            f"error: {args.out} already exists.\n"
            "The test split is frozen once created (data-and-splits.md). Refusing to overwrite it. "
            "If it genuinely has to be rebuilt, that is a decision to record first, then move the "
            "old file aside by hand.",
            file=sys.stderr,
        )
        return 3

    items = read_items(args.csv, Columns.load(args.columns))
    if not items:
        print("error: the export has no data rows", file=sys.stderr)
        return 2

    pilots = load_pilot_conversations(args.exp000_manifest)
    try:
        assignment, report = assign(items, pilot_conversations=pilots, seed=args.seed)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 4

    print("split assignment" + ("" if args.write else "  [DRY RUN — nothing written]"))
    print(f"  items {report['items']}  conversations {report['conversations']}")
    print(f"  counts {report['counts']}  targets {report['targets']}")
    print(f"  conversations per split {report['conversations_per_split']}")
    print(f"  EXP-000 conversations held out of test: {report['pilot_conversations_excluded_from_test']}")
    if args.exp000_manifest is None:
        print(
            "  WARNING: no --exp000-manifest, so no EXP-000 conversation was excluded.\n"
            "  data-and-splits.md forbids those items in the final test split, and this split is\n"
            "  frozen once written. Supply the manifest before --write."
        )

    if not args.write:
        print("\nRe-run with --write to freeze it.")
        return 0

    write_json(args.out, assignment)
    rid = run_id(REPO)
    write_json(
        args.runs_dir / rid / "config.json",
        {
            "experiment": "PE-002",
            "run_id": rid,
            "generated_at": utc_now(),
            "script_version": SCRIPT_VERSION,
            **git_state(REPO),
            "step": "make_split",
            "seed": args.seed,
            "input_sha256": sha256_file(args.csv),
            "split_assignment_sha256": sha256_file(args.out),
            "exp000_manifest_supplied": args.exp000_manifest is not None,
            **{f"report_{k}": v for k, v in report.items() if k != "seed"},
        },
    )
    print(f"\nwrote {args.out}  (local only, gitignored)")
    print(f"wrote {args.runs_dir / rid / 'config.json'}  (its hash is the reproducibility record)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
