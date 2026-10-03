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
import thresholds

#: The sheet's columns. The last three are always empty: the annotator fills them in.
SHEET_COLUMNS = (
    "item_id", "conversation_id", "turn_index", "field", "field_type", "field_description",
    "context", "turn_role", "turn_text", "label", "value", "notes",
)
EMPTY_COLUMNS = ("label", "value", "notes")

#: The label vocabulary from the experiment record, written to a reference file for the
#: annotators. This is not the annotation guideline, which the record says a human writes.
LABEL_VOCABULARY = (
    "NO-OP", "VALUE", "ABSTAIN:insufficient", "ABSTAIN:ambiguous", "ABSTAIN:conflicting",
    "HEDGED",
)

#: Pre-registered in thresholds.py. "random" is the remainder, drawn without requiring a cue.
DEFAULT_QUOTAS = dict(thresholds.SAMPLING_QUOTAS)

#: Where an item's conversation came from. Recorded in the manifest and NEVER in a sheet: an
#: annotator who could see "synthetic" would label it differently from a real turn, and the
#: whole point of reporting the two subsets separately is that the labels are blind to which is
#: which. Kapardhi's decision, 2026-10-03.
SOURCE_REAL = "real"
SOURCE_SYNTHETIC = "synthetic"

#: EXP-000 is an inter-annotator design with two annotators, named only "A" and "B". No personal
#: name goes into a sheet, the manifest or any other annotation artifact: which person is which
#: letter is the researcher's to know and is deliberately not recorded here.
DEFAULT_ANNOTATORS = ("A", "B")

#: Printed in place of a synthetic set's per-stratum counts. Kapardhi, 2026-10-03: during the v3
#: sampling run the synthetic set's stratum counts (hedge 13, correction 5, code-mixed 13) went
#: to Annotator A's terminal before labelling. No item-level or row-level information was shown
#: and Annotator B saw nothing, so no label is known to be affected, but an annotator who knows
#: how many hedges a set holds has an expectation to meet. Totals only, by default.
STRATA_WITHHELD = ("per-stratum counts withheld for this set: an annotator who knows how "
                   "many hedges or corrections it holds has an expectation to meet.\n"
                   "  They are in the manifest; --show-synthetic-strata prints them here.")
STRATA_WITHHELD_SHORT = "per-stratum counts withheld (see above)"


class SamplerError(Exception):
    pass


def load_field_keywords(path: str | Path | None) -> dict | None:
    """Optional local overrides for the field-mention keyword lists.

    Locality names are corpus-specific and cannot be enumerated in this repository, so this file
    is how the researcher adds real ones. It is read on his machine and nothing from it is
    written into a sheet or into runs/, so the names never leave that machine through this tool.

    A list given here REPLACES the built-in list for that field; a field left out keeps its
    built-in list.
    """
    if path is None:
        return None
    import yaml

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    entries = raw.get("field_keywords") if isinstance(raw, dict) else None
    if not entries:
        raise SamplerError(f"{path}: expected a non-empty 'field_keywords:' mapping")
    unknown = sorted(set(entries) - set(thresholds.FIELD_KEYWORDS))
    if unknown:
        raise SamplerError(
            f"{path}: field_keywords names field(s) {unknown} that are not in the pilot field "
            f"list {sorted(thresholds.FIELD_KEYWORDS)}")
    merged = {field: tuple(words) for field, words in thresholds.FIELD_KEYWORDS.items()}
    for field, words in entries.items():
        if not words:
            raise SamplerError(f"{path}: field_keywords[{field}] is empty")
        merged[field] = tuple(str(w) for w in words)
    return merged


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


def candidate_turns(conversations: dict[str, list[dict]], *, context_turns: int,
                    keywords=None, source: str = SOURCE_REAL) -> tuple[list[dict], dict]:
    """Eligible target turns, each with its context window and strata. Returns (turns, census).

    Only a customer turn of real text can be a target. Seller turns and media placeholders stay
    in the **context**, where the annotator needs them to apply rule Q3, but are never the turn
    being labelled: a seller target is NO-OP by construction and measures nothing.

    The census counts every turn by why it was or was not eligible. It exists because the
    researcher needs to know whether the corpus can support the quotas *before* anyone labels,
    not after a void run.
    """
    out = []
    census = {
        "turns_total": 0,
        "eligible_targets": 0,
        "rejected": {},
        "by_stratum": {name: 0 for name in cues.STRATA},
        "field_mentions": {field: 0 for field in (keywords or thresholds.FIELD_KEYWORDS)},
        "code_mixed_cue_hits": 0,
        "source": source,
    }
    for conversation_id, rows in sorted(conversations.items()):
        for position, turn in enumerate(rows):
            census["turns_total"] += 1
            reason = cues.target_rejection(turn)
            if reason is not None:
                census["rejected"][reason] = census["rejected"].get(reason, 0) + 1
                continue
            context = rows[max(0, position - context_turns):position]
            strata = cues.strata_for(turn, context, keywords=keywords)
            census["eligible_targets"] += 1
            for name in strata:
                census["by_stratum"][name] = census["by_stratum"].get(name, 0) + 1
            for field in cues.fields_mentioned(turn.get("text", ""), keywords):
                census["field_mentions"][field] = census["field_mentions"].get(field, 0) + 1
            if cues.has_code_mixed_cue(turn.get("text", "")):
                census["code_mixed_cue_hits"] += 1
            out.append({
                "conversation_id": conversation_id,
                "turn_index": turn.get("turn_index", position),
                "turn": turn,
                "context": context,
                "strata": strata,
                "source": source,
            })
    return out, census


def choose_turns(candidates: list[dict], *, n_turns: int, seed: int,
                 quotas: dict[str, float] | None = None,
                 all_strata: tuple[str, ...] = (),
                 random_topup: bool = True) -> tuple[list[dict], dict]:
    """Fill each stratum's quota first, then top up at random. Returns (turns, report).

    Quotas are targets, not guarantees: a corpus with few corrections cannot be made to have
    more. The shortfall is reported rather than silently absorbed, because an under-enriched
    sample changes what EXP-000's agreement numbers mean.
    """
    quotas = DEFAULT_QUOTAS if quotas is None else quotas
    rng = random.Random(seed)
    by_key = {(c["conversation_id"], c["turn_index"]): c for c in candidates}
    chosen: dict[tuple, dict] = {}
    report = {"targets": {}, "achieved": {}, "shortfall": {},
              "eligible_per_stratum": {}, "quotas": dict(quotas)}

    # A stratum named in `all_strata` contributes every eligible turn it has, before any quota
    # runs and regardless of n_turns. "Take all of them" has to win over a share of a target, or
    # the flag would mean nothing on a corpus where the stratum is larger than the request.
    for stratum in sorted(all_strata):
        for key in sorted((k for k, c in by_key.items() if stratum in c["strata"]),
                          key=lambda k: (str(k[0]), k[1])):
            chosen.setdefault(key, by_key[key])
        report["targets"][stratum] = sum(
            1 for c in by_key.values() if stratum in c["strata"])
        report["achieved"][stratum] = report["targets"][stratum]
        report["shortfall"][stratum] = 0
        report["eligible_per_stratum"][stratum] = report["targets"][stratum]
    report["all_strata"] = list(all_strata)
    report["taken_wholesale"] = len(chosen)

    cue_quotas = {s: share for s, share in quotas.items()
                  if s != thresholds.RANDOM_STRATUM and s not in all_strata}
    for stratum, share in sorted(cue_quotas.items()):
        target = min(int(round(share * n_turns)), n_turns)
        pool = sorted(
            (k for k, c in by_key.items() if stratum in c["strata"] and k not in chosen),
            key=lambda k: (str(k[0]), k[1]),
        )
        report["eligible_per_stratum"][stratum] = sum(
            1 for c in by_key.values() if stratum in c["strata"])
        take = pool if len(pool) <= target else rng.sample(pool, target)
        for key in take:
            if len(chosen) < n_turns:
                chosen[key] = by_key[key]
        report["targets"][stratum] = target
        report["achieved"][stratum] = sum(1 for k in take if k in chosen)
        report["shortfall"][stratum] = max(0, target - report["achieved"][stratum])

    # The random remainder: whatever is left, cue or no cue. Its target is the quota's share,
    # but it also absorbs any shortfall the cue strata could not fill, so n_turns is still met
    # where the corpus allows.
    remaining = sorted((k for k in by_key if k not in chosen), key=lambda k: (str(k[0]), k[1]))
    random_target = n_turns - sum(report["targets"].values())
    short = n_turns - len(chosen)
    drawn = 0
    report["random_topup"] = bool(random_topup)
    if random_topup and short > 0 and remaining:
        for key in rng.sample(remaining, min(short, len(remaining))):
            chosen[key] = by_key[key]
            drawn += 1
    report["eligible_per_stratum"][thresholds.RANDOM_STRATUM] = len(by_key)
    report["targets"][thresholds.RANDOM_STRATUM] = max(0, random_target)
    report["achieved"][thresholds.RANDOM_STRATUM] = drawn
    report["shortfall"][thresholds.RANDOM_STRATUM] = max(0, n_turns - len(chosen))
    report["turns_requested"] = n_turns
    report["turns_selected"] = len(chosen)

    turns = sorted(chosen.values(), key=lambda c: (str(c["conversation_id"]), c["turn_index"]))
    return turns, report


def format_context(context: list[dict]) -> str:
    """Context lines labelled by role, not by SPEAKER_n.

    Rule Q3 turns on who said a thing, so an annotator who cannot tell the customer from the
    seller in the context cannot apply the guideline. The voided run's sheets showed SPEAKER_n.
    """
    return "\n".join(f"{cues.display_role(r)}: {r.get('text', '')}" for r in context)


def conversation_aliases(turns: list[dict], *, seed: int) -> dict[str, str]:
    """Sheet-facing ids for the sampled conversations, from one namespace for every source.

    Without this the source leaks through the id. Real conversations arrive as `conv_001` from
    the scrubber and synthetic ones as `syn_001`, so an item id of `syn_004#2#budget` tells an
    annotator the turn was written by a model -- which is exactly what keeping `source` out of
    the sheet was meant to prevent. The aliases are drawn in a seeded shuffle across the merged
    set, so neither the prefix nor the ordering carries the source.

    The mapping back to the true conversation ids is in the manifest, and `pilot_items.json`
    keeps the true ids, because test-split exclusion has to work against the real corpus.
    """
    true_ids = sorted({turn["conversation_id"] for turn in turns})
    shuffled = list(true_ids)
    random.Random(f"alias:{seed}").shuffle(shuffled)
    return {true_id: f"c{position:03d}" for position, true_id in enumerate(shuffled, start=1)}


def build_items(turns: list[dict], fields: list[dict], *, n_items: int,
                aliases: dict[str, str] | None = None) -> list[dict]:
    """One row per (field, turn), trimmed on a turn boundary.

    Trimming whole turns rather than individual fields keeps every presented turn fully
    labelled, so no annotator is asked about some fields of a turn and not others.
    """
    items, per_turn = [], len(fields)
    if per_turn == 0:
        raise SamplerError("the field list is empty")
    usable = max(1, n_items // per_turn)
    aliases = aliases or {}
    for turn in turns[:usable]:
        context = format_context(turn["context"])
        shown = aliases.get(turn["conversation_id"], turn["conversation_id"])
        for field in fields:
            items.append({
                "item_id": f"{shown}#{turn['turn_index']}#{field['name']}",
                "source": turn.get("source", SOURCE_REAL),
                "true_conversation_id": turn["conversation_id"],
                "conversation_id": shown,
                "turn_index": turn["turn_index"],
                "field": field["name"],
                "field_type": field["type"],
                "field_description": field["description"],
                "context": context,
                "turn_role": cues.display_role(turn["turn"]),
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
                # Projected onto SHEET_COLUMNS rather than written whole. An item carries
                # `source`, and a sheet must not: this makes that structural, so adding another
                # researcher-only key later cannot leak it into an annotator's view by default.
                writer.writerow({column: item.get(column, "") for column in SHEET_COLUMNS})
        written.append(path)
    return written


def report_census(census: dict, *, n_items: int, fields: int, out,
                  strata: bool = True) -> None:
    """What the corpus can support, printed BEFORE any sheet is written.

    The point is to make an under-supplied corpus visible while it can still be acted on. Run
    20261002T175103Z-f318529 was voided after labelling, and this is the number that would have
    predicted it: of its turns, the eligible-target count was a small fraction of the total.

    `strata=False` prints totals only, and is the default for a `--synthetic` set. During the
    v3 sampling run the synthetic set's per-stratum counts printed to Annotator A's terminal
    before labelling. A count like "hedge 13" tells an annotator how often to expect a
    phenomenon in the part of the item set that contains it, which is priming; the eligible
    total carries no such expectation. The counts are still written to the manifest, which is
    the researcher's file.
    """
    wanted_turns = max(1, n_items // max(1, fields))
    print(f"turns read: {census['turns_total']}", file=out)
    print(f"eligible targets (customer, text, >= {thresholds.MIN_TARGET_WORDS} words): "
          f"{census['eligible_targets']}", file=out)
    if census["rejected"]:
        shown = ", ".join(f"{reason} {count}"
                          for reason, count in sorted(census["rejected"].items()))
        print(f"  not eligible: {shown}", file=out)
    if strata:
        print(f"eligible per stratum: "
              f"{ {k: v for k, v in census['by_stratum'].items() if v} }", file=out)
        print(f"field mentions among eligible: "
              f"{ {k: v for k, v in census['field_mentions'].items() if v} }", file=out)
        if census.get("code_mixed_cue_hits"):
            print(f"of which matched a code-mixed cue: {census['code_mixed_cue_hits']} "
                  "(romanized Telugu/Hindi forms added 2026-10-03)", file=out)
    else:
        print(STRATA_WITHHELD, file=out)
    print(f"turns needed for --n-items {n_items} over {fields} fields: {wanted_turns}", file=out)
    if census["eligible_targets"] < wanted_turns:
        print(f"WARNING: only {census['eligible_targets']} eligible target(s) for "
              f"{wanted_turns} needed; the sample will be smaller than requested", file=out)
    if strata:
        for stratum, share in sorted(thresholds.SAMPLING_QUOTAS.items()):
            if stratum == thresholds.RANDOM_STRATUM:
                continue
            need = int(round(share * wanted_turns))
            have = census["by_stratum"].get(stratum, 0)
            if have < need:
                print(f"WARNING: stratum {stratum} wants {need} turn(s), corpus has {have}",
                      file=out)
    print(file=out)


def _count_by_source(items) -> dict[str, int]:
    out: dict[str, int] = {}
    for item in items:
        out[item["source"]] = out.get(item["source"], 0) + 1
    return out


def write_manifest(root: Path, items, turns, report, settings, orders=None) -> Path:
    """The researcher's record of how items were chosen. Annotators do not see this."""
    manifest = {
        "tool": "EXP-000 sample_items.py",
        "do_not_show_to_annotators": "Strata record why a turn was sampled. Showing a cue to an "
                                     "annotator would prime the label.",
        "agreement_design": "inter-annotator, two annotators named only A and B",
        "settings": settings,
        "enrichment": report,
        "corpus_census": settings.get("census"),
        "synthetic_enrichment": settings.get("synthetic_enrichment"),
        "synthetic_census": settings.get("synthetic_census"),
        "item_source": {item["item_id"]: item["source"] for item in items},
        "conversation_alias": settings.get("aliases") or {},
        "alias_note": "Sheets show the alias, never the true conversation id: a `syn_` prefix "
                      "would tell an annotator the turn was model-written. The true ids are "
                      "here and in pilot_items.json.",
        "items_by_source": _count_by_source(items),
        "source_note": "Item sources are recorded here and in no sheet. agreement.py --manifest "
                       "reads this map to report kappa for the real and synthetic subsets "
                       "separately. Only the real subset's verdict bears on ADR-003.",
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
        "note": "conversation_id here is the TRUE id, not the sheet alias, because exclusion "
                "has to match the real corpus.",
        "turns": [
            {"conversation_id": t["conversation_id"], "turn_index": t["turn_index"],
             "source": t.get("source", SOURCE_REAL)}
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
    parser.add_argument("--synthetic", type=Path, default=None, metavar="DIR",
                        help="a second conversation set, sampled alongside --input. Its items "
                             "are marked source=synthetic in the manifest and nowhere else")
    parser.add_argument("--synthetic-turns", type=int, default=16,
                        help="turns to draw from --synthetic, using the normal quotas")
    parser.add_argument("--all-stratum", action="append", default=None, metavar="NAME",
                        choices=list(cues.STRATA),
                        help="take EVERY eligible turn in this stratum from --input instead of "
                             "a quota share; repeatable")
    parser.add_argument("--no-random-topup", action="store_true",
                        help="do not pad the real set with cue-free turns to reach --n-items")
    parser.add_argument("--show-synthetic-strata", action="store_true",
                        help="print the --synthetic set's per-stratum counts, which are "
                             "withheld by default so that labelling them is not primed by "
                             "knowing how many hedges or corrections they contain. The counts "
                             "are in the manifest either way; use this only when nobody who "
                             "will label the set can see the output")
    parser.add_argument("--census-only", action="store_true",
                        help="print the census and write nothing, to see what a corpus can "
                             "support before committing to a sample")
    parser.add_argument("--field-keywords", type=Path, default=None,
                        help="optional YAML of field_keywords to replace the built-in lists, "
                             "for locality names this repository cannot hold")
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
    keywords = load_field_keywords(args.field_keywords)
    all_strata = tuple(args.all_stratum or ())

    candidates, census = candidate_turns(conversations, context_turns=args.context_turns,
                                         keywords=keywords, source=SOURCE_REAL)
    report_census(census, n_items=args.n_items, fields=len(fields), out=out)

    synthetic_candidates: list[dict] = []
    synthetic_census = None
    synthetic_conversations: dict = {}
    if args.synthetic:
        safety.assert_disjoint(args.synthetic, args.output)
        synthetic_conversations = load_conversations(args.synthetic)
        overlap = sorted(set(synthetic_conversations) & set(conversations))
        if overlap:
            raise SamplerError(
                f"conversation id(s) {overlap[:5]} appear in both --input and --synthetic. "
                "Items are keyed by conversation and turn, so a collision would merge two "
                "different conversations into one item id.")
        synthetic_candidates, synthetic_census = candidate_turns(
            synthetic_conversations, context_turns=args.context_turns, keywords=keywords,
            source=SOURCE_SYNTHETIC)
        print(f"--- synthetic set: {args.synthetic} ---", file=out)
        report_census(synthetic_census, n_items=args.synthetic_turns * len(fields),
                      fields=len(fields), out=out, strata=args.show_synthetic_strata)

    if args.census_only:
        print("--census-only: nothing was written.", file=out)
        return 0

    if not candidates and not synthetic_candidates:
        raise SamplerError(
            "no turn in either corpus can be a target. A target must be a customer turn of "
            f"real text with at least {thresholds.MIN_TARGET_WORDS} words; "
            f"{census['turns_total']} turns were read from --input and all were rejected "
            f"({census['rejected']}).")
    n_turns = max(1, args.n_items // len(fields))
    turns, report = choose_turns(candidates, n_turns=n_turns, seed=args.seed,
                                 all_strata=all_strata,
                                 random_topup=not args.no_random_topup)
    synthetic_report = None
    if synthetic_candidates:
        synthetic_turns, synthetic_report = choose_turns(
            synthetic_candidates, n_turns=args.synthetic_turns, seed=args.seed + 1)
        turns = turns + synthetic_turns

    # Every selected turn becomes len(fields) items; nothing is trimmed, because the real set's
    # size is decided by --all-stratum rather than by --n-items.
    aliases = conversation_aliases(turns, seed=args.seed)
    items = build_items(turns, fields, n_items=len(turns) * len(fields), aliases=aliases)
    by_source = {}
    for item in items:
        by_source[item["source"]] = by_source.get(item["source"], 0) + 1
    print(f"ITEMS TO BE WRITTEN: {len(items)} "
          f"({len(turns)} turns x {len(fields)} fields) {by_source}", file=out)
    if len(items) > args.n_items:
        reasons = []
        if all_strata:
            reasons.append(f"--all-stratum takes every turn in {list(all_strata)} regardless "
                           "of the request")
        if synthetic_candidates:
            reasons.append(f"--n-items governs --input only, and --synthetic-turns "
                           f"{args.synthetic_turns} adds to it")
        print(f"  this exceeds --n-items {args.n_items}"
              + ("; " + "; ".join(reasons) if reasons else ""), file=out)
    print(file=out)

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
        "target_roles": list(thresholds.TARGET_ROLES),
        "min_target_words": thresholds.MIN_TARGET_WORDS,
        "field_keywords_overridden": bool(args.field_keywords),
        "census": census,
        "synthetic_census": synthetic_census,
        "synthetic_strata_printed": bool(args.synthetic) and args.show_synthetic_strata,
        "synthetic_strata_note": "Whether this run printed the synthetic set's per-stratum "
                                 "counts to a terminal. False is the default: an annotator who "
                                 "knows how many hedges a set holds has an expectation to meet. "
                                 "Recorded so a run can be audited for that exposure.",
        "synthetic_enrichment": synthetic_report,
        "synthetic_turns_requested": args.synthetic_turns if args.synthetic else None,
        "all_strata": list(all_strata),
        "random_topup": not args.no_random_topup,
        "aliases": {alias: true_id for true_id, alias in aliases.items()},
    }

    orders, order_report = shuffled_orders(items, annotators, seed=args.seed)
    sheets = write_sheets(root, orders)
    write_manifest(root, items, turns, report, settings, orders=order_report)
    write_pilot_items(root, turns)
    write_label_reference(root)

    print(f"conversations read: {len(conversations)} real"
          + (f" + {len(synthetic_conversations)} synthetic" if synthetic_candidates else ""),
          file=out)
    print(f"real: {len(candidates)} eligible, "
          f"{sum(1 for x in turns if x['source'] == SOURCE_REAL)} sampled", file=out)
    if synthetic_candidates:
        print(f"synthetic: {len(synthetic_candidates)} eligible, "
              f"{sum(1 for x in turns if x['source'] == SOURCE_SYNTHETIC)} sampled", file=out)
    print(f"items: {len(items)} ({len(fields)} fields x {len(turns)} turns) {by_source}",
          file=out)
    print(f"real enrichment achieved: {report['achieved']}", file=out)
    if any(report["shortfall"].values()):
        print(f"real enrichment shortfall: "
              f"{ {k: v for k, v in report['shortfall'].items() if v} }", file=out)
    if synthetic_report:
        if args.show_synthetic_strata:
            print(f"synthetic enrichment achieved: {synthetic_report['achieved']}", file=out)
            if any(synthetic_report["shortfall"].values()):
                print(f"synthetic enrichment shortfall: "
                      f"{ {k: v for k, v in synthetic_report['shortfall'].items() if v} }",
                      file=out)
        else:
            print(f"synthetic enrichment: "
                  f"{sum(synthetic_report['achieved'].values())} turn(s) sampled", file=out)
            print(f"  {STRATA_WITHHELD_SHORT}", file=out)
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
