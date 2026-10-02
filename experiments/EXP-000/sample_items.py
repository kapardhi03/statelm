#!/usr/bin/env python3
"""EXP-000 item sampler and annotation-sheet generator. Runs locally.

Reads scrubbed conversations, samples (field, turn) items enriched for corrections, hedges and
multi-speaker stretches, and writes one annotation sheet per annotator with **empty label
columns**.

Two rules from the experiment record shape every decision here:

- *"Pre-label items, suggest labels, or act as an annotator"* is forbidden. The sheets carry
  context and a field name and nothing else. The cue that caused a turn to be sampled is written
  to the manifest the researcher reads, never to the sheet an annotator reads, because an
  annotator who could see "matched a hedge cue" would be primed toward HEDGED.
- *"Items used here are pilot items and must not enter the eventual test split."* Every sampled
  turn is recorded in `pilot_items.json` by conversation and turn index so it can be excluded
  later.

    python sample_items.py --input ../../data/scrubbed/EXP-000 \
        --output ../../data/scrubbed/EXP-000/annotation --fields fields.yaml
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from pathlib import Path

import cues
import safety

#: The sheet's columns. The last three are always empty: the annotator fills them in.
SHEET_COLUMNS = (
    "item_id", "conversation_id", "turn_index", "field", "field_type", "field_description",
    "context", "turn_speaker", "turn_text", "label", "value", "notes",
)
EMPTY_COLUMNS = ("label", "value", "notes")

#: The label vocabulary from the experiment record, written to a reference file for the
#: annotators. This is not the annotation guideline, which the record says a human writes.
LABEL_VOCABULARY = (
    "NO-OP", "VALUE", "ABSTAIN:insufficient", "ABSTAIN:ambiguous", "ABSTAIN:conflicting",
    "HEDGED",
)

DEFAULT_QUOTAS = {"correction": 0.25, "hedge": 0.25, "multi_speaker": 0.2}

#: EXP-000 is an inter-annotator design with two annotators, named only "A" and "B". No personal
#: name goes into a sheet, the manifest or any other annotation artifact: which person is which
#: letter is the researcher's to know and is deliberately not recorded here.
DEFAULT_ANNOTATORS = ("A", "B")


class SamplerError(Exception):
    pass


def load_fields(path: str | Path) -> list[dict]:
    """Load the field list. Required: there is no agreed schema to fall back on."""
    import yaml

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = raw.get("fields") if isinstance(raw, dict) else None
    if not entries:
        raise SamplerError(f"{path}: expected a non-empty 'fields:' list")
    fields = []
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict) or "name" not in entry:
            raise SamplerError(f"{path}: fields[{i}] needs at least a 'name'")
        fields.append({
            "name": str(entry["name"]),
            "type": str(entry.get("type", "")),
            "description": str(entry.get("description", "")),
        })
    return fields


def load_conversations(input_dir: str | Path) -> dict[str, list[dict]]:
    """Read the scrubbed JSONL files, keeping each conversation's turn order."""
    root = Path(input_dir).expanduser().resolve()
    if not root.is_dir():
        raise SamplerError(f"{root} is not a directory")
    out: dict[str, list[dict]] = {}
    for path in sorted(root.glob("*.jsonl")):
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        for row in rows:
            out.setdefault(row["conversation_id"], []).append(row)
    for rows in out.values():
        rows.sort(key=lambda r: r.get("turn_index", 0))
    if not out:
        raise SamplerError(f"no .jsonl conversations found under {root}")
    return out


def candidate_turns(conversations: dict[str, list[dict]], *, context_turns: int) -> list[dict]:
    """Every turn, with its preceding context window and its strata."""
    out = []
    for conversation_id, rows in sorted(conversations.items()):
        for position, turn in enumerate(rows):
            if not (turn.get("text") or "").strip():
                continue
            context = rows[max(0, position - context_turns):position]
            out.append({
                "conversation_id": conversation_id,
                "turn_index": turn.get("turn_index", position),
                "turn": turn,
                "context": context,
                "strata": cues.strata_for(turn, context),
            })
    return out


def choose_turns(candidates: list[dict], *, n_turns: int, seed: int,
                 quotas: dict[str, float] | None = None) -> tuple[list[dict], dict]:
    """Fill each stratum's quota first, then top up at random. Returns (turns, report).

    Quotas are targets, not guarantees: a corpus with few corrections cannot be made to have
    more. The shortfall is reported rather than silently absorbed, because an under-enriched
    sample changes what EXP-000's agreement numbers mean.
    """
    quotas = DEFAULT_QUOTAS if quotas is None else quotas
    rng = random.Random(seed)
    by_key = {(c["conversation_id"], c["turn_index"]): c for c in candidates}
    chosen: dict[tuple, dict] = {}
    report = {"targets": {}, "achieved": {}, "shortfall": {}}

    for stratum, share in sorted(quotas.items()):
        target = min(int(round(share * n_turns)), n_turns)
        pool = sorted(
            (k for k, c in by_key.items() if stratum in c["strata"] and k not in chosen),
            key=lambda k: (str(k[0]), k[1]),
        )
        take = pool if len(pool) <= target else rng.sample(pool, target)
        for key in take:
            if len(chosen) < n_turns:
                chosen[key] = by_key[key]
        report["targets"][stratum] = target
        report["achieved"][stratum] = len(take)
        report["shortfall"][stratum] = max(0, target - len(take))

    remaining = sorted((k for k in by_key if k not in chosen), key=lambda k: (str(k[0]), k[1]))
    short = n_turns - len(chosen)
    if short > 0 and remaining:
        for key in rng.sample(remaining, min(short, len(remaining))):
            chosen[key] = by_key[key]

    turns = sorted(chosen.values(), key=lambda c: (str(c["conversation_id"]), c["turn_index"]))
    return turns, report


def format_context(context: list[dict]) -> str:
    return "\n".join(f"{r.get('speaker_id', '?')}: {r.get('text', '')}" for r in context)


def build_items(turns: list[dict], fields: list[dict], *, n_items: int) -> list[dict]:
    """One row per (field, turn), trimmed on a turn boundary.

    Trimming whole turns rather than individual fields keeps every presented turn fully
    labelled, so no annotator is asked about some fields of a turn and not others.
    """
    items, per_turn = [], len(fields)
    if per_turn == 0:
        raise SamplerError("the field list is empty")
    usable = max(1, n_items // per_turn)
    for turn in turns[:usable]:
        context = format_context(turn["context"])
        for field in fields:
            items.append({
                "item_id": f"{turn['conversation_id']}#{turn['turn_index']}#{field['name']}",
                "conversation_id": turn["conversation_id"],
                "turn_index": turn["turn_index"],
                "field": field["name"],
                "field_type": field["type"],
                "field_description": field["description"],
                "context": context,
                "turn_speaker": turn["turn"].get("speaker_id", ""),
                "turn_text": turn["turn"].get("text", ""),
                "label": "", "value": "", "notes": "",
            })
    return items


def annotator_seed(base_seed: int, name: str, attempt: int = 0) -> int:
    """A per-annotator seed derived from the run seed, so each order is reproducible.

    Derived rather than passed in so one `--seed` reproduces the whole run, sheet orders
    included, and so adding an annotator does not change anyone else's order.
    """
    digest = hashlib.sha256(f"{base_seed}:{name}:{attempt}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


def turn_key(item: dict) -> tuple[str, int]:
    return (item["conversation_id"], item["turn_index"])


def turn_blocks(items: list[dict]) -> dict[tuple[str, int], list[dict]]:
    """Items grouped by turn, in the order they were built, each block keeping field order."""
    blocks: dict[tuple[str, int], list[dict]] = {}
    for item in items:
        blocks.setdefault(turn_key(item), []).append(item)
    return blocks


#: What gets permuted. Turn blocks rather than individual items: the five fields of one turn
#: stay together, so an annotator reads a turn's context once and answers every question about
#: it, instead of meeting the same context five times scattered through the sheet. Kapardhi's
#: decision, 2026-10-02.
SHUFFLE_UNIT = "turn"


def shuffled_orders(items: list[dict], annotators: list[str], *,
                    seed: int) -> tuple[dict[str, list[dict]], dict]:
    """Each annotator gets the same items with the turn blocks in their own seeded order.

    Different orders mean neither annotator can anchor on the other's sequence, and a
    disagreement cannot be an artefact of both having read the items in the same run-up. The
    item *set* is identical for everyone; only the order of the turn blocks differs. Within a
    block the fields keep `fields.yaml`'s order for everyone, so the only thing that varies
    between sheets is which turn comes next.

    Identical orders are re-drawn with a bumped attempt counter. With one turn, or with more
    annotators than there are distinct permutations, that is impossible, so the report says so
    rather than the function looping.
    """
    blocks = turn_blocks(items)
    keys = list(blocks)
    orders: dict[str, list[dict]] = {}
    turn_orders: dict[str, list] = {}
    report: dict = {"shuffle_unit": SHUFFLE_UNIT, "turns": len(keys), "seeds": {},
                    "collisions_redrawn": 0, "orders_distinct": True}

    for name in annotators:
        for attempt in range(8):
            derived = annotator_seed(seed, name, attempt)
            candidate = list(keys)
            random.Random(derived).shuffle(candidate)
            if any(candidate == existing for existing in turn_orders.values()):
                report["collisions_redrawn"] += 1
                continue
            turn_orders[name] = candidate
            orders[name] = [item for key in candidate for item in blocks[key]]
            report["seeds"][name] = derived
            break
        else:
            turn_orders[name] = list(keys)
            orders[name] = list(items)
            report["seeds"][name] = annotator_seed(seed, name)
            report["orders_distinct"] = False

    if not report["orders_distinct"]:
        report["note"] = (
            f"Two sheets share a turn order. With {len(keys)} turn(s) and "
            f"{len(annotators)} annotators a distinct permutation for each does not exist; "
            "the orders are recorded as they are.")
    report["turn_order"] = {name: [f"{c}#{t}" for c, t in order]
                            for name, order in turn_orders.items()}
    report["item_order"] = {name: [item["item_id"] for item in rows]
                            for name, rows in orders.items()}
    return orders, report


def write_sheets(root: Path, orders: dict[str, list[dict]]) -> list[Path]:
    """One sheet per annotator: the same items, each in that annotator's own order."""
    written = []
    for name, rows in orders.items():
        target = f"sheet_{name}.csv"
        path = safety.assert_within(root, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(SHEET_COLUMNS))
            writer.writeheader()
            for item in rows:
                writer.writerow(item)
        written.append(path)
    return written


def write_manifest(root: Path, items, turns, report, settings, orders=None) -> Path:
    """The researcher's record of how items were chosen. Annotators do not see this."""
    manifest = {
        "tool": "EXP-000 sample_items.py",
        "do_not_show_to_annotators": "Strata record why a turn was sampled. Showing a cue to an "
                                     "annotator would prime the label.",
        "agreement_design": "inter-annotator, two annotators named only A and B",
        "settings": settings,
        "enrichment": report,
        "sheet_order": orders or {},
        "items": len(items),
        "turns": len(turns),
        "turn_strata": [
            {
                "conversation_id": t["conversation_id"],
                "turn_index": t["turn_index"],
                "strata": sorted(t["strata"]),
            }
            for t in turns
        ],
    }
    return safety.write_json(root, "manifest.json", manifest)


def write_pilot_items(root: Path, turns) -> Path:
    """Ids only, so these turns can be excluded from the eventual test split."""
    payload = {
        "purpose": "EXP-000 pilot items. These turns must never enter the final test split.",
        "turns": [
            {"conversation_id": t["conversation_id"], "turn_index": t["turn_index"]}
            for t in turns
        ],
    }
    return safety.write_json(root, "pilot_items.json", payload)


def write_label_reference(root: Path) -> Path:
    body = (
        "EXP-000 label vocabulary\n"
        "========================\n\n"
        "Use exactly one of these in the 'label' column:\n\n"
        + "".join(f"  {label}\n" for label in LABEL_VOCABULARY)
        + "\nFill 'value' only for VALUE. Use 'notes' for anything you want to flag.\n\n"
          "This file is the vocabulary, not the annotation guideline. The guideline is written\n"
          "and approved by the researcher; label nothing until you have it.\n"
    )
    return safety.write_text(root, "labels_reference.txt", body)


def main(argv=None, out=sys.stdout) -> int:
    parser = argparse.ArgumentParser(description="EXP-000 item sampler (run locally)")
    parser.add_argument("--input", required=True, type=Path, help="scrubbed JSONL directory")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fields", required=True, type=Path, help="fields.yaml")
    parser.add_argument("--n-items", type=int, default=80, help="target (field, turn) items")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--context-turns", type=int, default=6)
    parser.add_argument("--annotators", nargs="+", default=list(DEFAULT_ANNOTATORS),
                        metavar="NAME",
                        help="sheet names, space- or comma-separated; one sheet each. Use "
                             "letters, not people's names: no personal name belongs in an "
                             "annotation artifact.")
    args = parser.parse_args(argv)

    safety.assert_disjoint(args.input, args.output)
    root = safety.resolve_root(args.output)
    fields = load_fields(args.fields)
    conversations = load_conversations(args.input)
    candidates = candidate_turns(conversations, context_turns=args.context_turns)
    n_turns = max(1, args.n_items // len(fields))
    turns, report = choose_turns(candidates, n_turns=n_turns, seed=args.seed)
    items = build_items(turns, fields, n_items=args.n_items)

    annotators = [part.strip() for chunk in args.annotators
                  for part in str(chunk).split(",") if part.strip()]
    if not annotators:
        raise SamplerError("--annotators named nobody")
    if len(annotators) != len(set(annotators)):
        raise SamplerError(f"--annotators repeats a name: {annotators}")
    settings = {
        "n_items_requested": args.n_items, "seed": args.seed,
        "context_turns": args.context_turns, "fields": [f["name"] for f in fields],
        "annotators": annotators, "quotas": DEFAULT_QUOTAS,
        "agreement_design": "inter_annotator" if len(annotators) > 1 else "single_sheet",
    }

    orders, order_report = shuffled_orders(items, annotators, seed=args.seed)
    sheets = write_sheets(root, orders)
    write_manifest(root, items, turns, report, settings, orders=order_report)
    write_pilot_items(root, turns)
    write_label_reference(root)

    print(f"conversations read: {len(conversations)}", file=out)
    print(f"candidate turns: {len(candidates)}; sampled: {len(turns)}", file=out)
    print(f"items: {len(items)} ({len(fields)} fields x {len(turns)} turns)", file=out)
    print(f"enrichment achieved: {report['achieved']}", file=out)
    if any(report["shortfall"].values()):
        print(f"enrichment shortfall: "
              f"{ {k: v for k, v in report['shortfall'].items() if v} }", file=out)
    print(f"sheets: {', '.join(p.name for p in sheets)} (label columns are empty)", file=out)
    print(f"each sheet holds the same items with the turn blocks in its own seeded order "
          f"({order_report['turns']} turns); the orders are in the manifest", file=out)
    if not order_report["orders_distinct"]:
        print(f"WARNING: {order_report['note']}", file=out)
    print(f"wrote {root}", file=out)
    print("The manifest records why each turn was sampled. Do not show it to annotators.",
          file=out)
    if len(annotators) == 1:
        print("One annotator: the record's fallback is intra-annotator agreement, relabelled "
              "after at least a week, blind to the first labels, and reported as intra-, not "
              "inter-annotator.", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
