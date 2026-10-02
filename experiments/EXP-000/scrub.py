#!/usr/bin/env python3
"""EXP-000 PII scrubber. Runs locally on Kapardhi's machine, never in a Claude session.

Reads CSV / XLSX / JSON exports from an input folder, replaces personal identifiers with
per-conversation placeholders, and writes one JSONL per conversation plus two reports. It makes
three guarantees about itself, each covered by a test:

1. It writes nothing outside the output folder passed to --output.
2. It never modifies the input.
3. It makes no network calls.

Bare amounts are preserved. See `detectors` for why, and README.md for what this does not
guarantee.

    python scrub.py --input data/raw/arthryx --output data/scrubbed/EXP-000 \
        --columns columns.yaml [--roles roles.csv] [--dry-run] [--check]
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import detectors
import parsers
import report
import safety
import timestamps
from placeholders import PlaceholderMap

VERSION = "0.1.0"
SCHEMA = "exp000-pilot-v1"
AUDIT_DIRNAME = "_audit"
AUDIT_FILENAME = "audit.sensitive.jsonl"
SUMMARY_FILENAME = "summary.json"


def load_roles(path: str | Path | None) -> dict[str, str]:
    """speaker,role rows. Only consulted when the export has no role column."""
    if not path:
        return {}
    with Path(path).open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames or "speaker" not in reader.fieldnames:
            raise parsers.ColumnMapError(f"{path}: expected a header with 'speaker' and 'role'")
        return {
            (row.get("speaker") or "").strip(): (row.get("role") or "").strip() or "unknown"
            for row in reader
            if (row.get("speaker") or "").strip()
        }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def apply_redactions(text: str, spans, pmap: PlaceholderMap) -> tuple[str, list[tuple[str, str, str]]]:
    """Replace right to left so earlier offsets stay valid. Returns (text, replacements)."""
    out, made = text, []
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        # The token is keyed on the canonical identity so surface variants collapse; the audit
        # records the surface form that was actually removed.
        token = pmap.token(span.category, span.canonical or span.text)
        made.append((span.category, span.text, token))
        out = out[: span.start] + token + out[span.end :]
    return out, list(reversed(made))


def scrub_conversation(messages, conversation_id, *, address_clauses, amount_window,
                       roles_map, date_format, source_hashes):
    """One conversation in, (jsonl rows, audit entries, speaker tokens, stats) out."""
    pmap = PlaceholderMap()
    # Seed person ordinals in speaker first-appearance order, so SPEAKER_n and [PERSON_n] agree.
    roster: list[str] = []
    for message in messages:
        if message.speaker and message.speaker not in roster:
            roster.append(message.speaker)
            pmap.token("PERSON", message.speaker)

    speaker_tokens, rows, entries = {}, [], []
    unmapped, unparsed = set(), 0
    created_at = datetime.now(timezone.utc).isoformat()

    for turn_index, message in enumerate(messages):
        index = pmap.index_of("PERSON", message.speaker) if message.speaker else None
        speaker_id = f"SPEAKER_{index}" if index else "SPEAKER_UNKNOWN"
        if message.speaker:
            speaker_tokens[message.speaker] = speaker_id

        role = message.role or roles_map.get(message.speaker) or "unknown"
        if role == "unknown" and message.speaker:
            unmapped.add(message.speaker)

        spans = detectors.find_all(message.text, roster, address_clauses=address_clauses)
        kept = detectors.redactions(detectors.resolve(spans), amount_window=amount_window)
        text, made = apply_redactions(message.text, kept, pmap)

        iso, raw = timestamps.parse(message.timestamp_raw, date_format=date_format)
        if iso is None and raw:
            unparsed += 1

        rows.append({
            "schema": SCHEMA,
            "conversation_id": conversation_id,
            "turn_index": turn_index,
            "timestamp": iso,
            "timestamp_raw": raw,
            "speaker_id": speaker_id,
            "speaker_role": role,
            "text": text,
            "provenance": {
                "source": "human",
                "generator": None,
                "labeler": None,
                "created_at": created_at,
                "split": None,
                "scrubber_version": VERSION,
                "source_file": message.source_file,
                "source_row": message.source_row,
                "source_sha256": source_hashes.get(message.source_file),
            },
        })
        entries += [
            report.AuditEntry(
                conversation_id=conversation_id, turn_index=turn_index,
                source_file=message.source_file, source_row=message.source_row,
                category=category, original=original, token=token,
            )
            for category, original, token in made
        ]

    return rows, entries, speaker_tokens, pmap, sorted(unmapped), unparsed


def residual_scan(rows_by_conversation: dict[str, list[dict]]) -> dict:
    """Re-read the scrubbed text and look for identifiers that should no longer be there.

    This checks the output, which is where a miss actually matters. It cannot find a missed
    name, only a missed structured identifier.
    """
    hits = Counter()
    examples: dict[str, int] = {}
    for conversation_id, rows in rows_by_conversation.items():
        for row in rows:
            text = row["text"]
            found = [
                s for s in detectors.resolve(detectors.find_all(text))
                if s.category in {"EMAIL", "UPI", "IFSC", "CARD", "ACCOUNT", "PHONE", "TXNREF"}
            ]
            for span in found:
                hits[span.category] += 1
                examples.setdefault(f"{conversation_id}#{row['turn_index']}", 0)
                examples[f"{conversation_id}#{row['turn_index']}"] += 1
    return {
        "checked_messages": sum(len(r) for r in rows_by_conversation.values()),
        "residual_hits_by_category": dict(hits),
        "messages_with_hits": len(examples),
        "note": "Counts only; no text. A non-zero count means read the audit and tighten a rule.",
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="EXP-000 PII scrubber (run locally)")
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--columns", required=True, type=Path, help="columns.yaml")
    parser.add_argument("--roles", type=Path, default=None, help="speaker,role CSV")
    parser.add_argument("--date-format", default=None, help="strptime format tried before defaults")
    parser.add_argument("--amount-window", type=int, default=detectors.AMOUNT_WINDOW)
    parser.add_argument("--address-clauses", action="store_true",
                        help="also redact locality keyword clauses (blunt; removes ordinary text)")
    parser.add_argument("--keep-conversation-ids", action="store_true",
                        help="use source ids as filenames; they may themselves be identifying")
    parser.add_argument("--dry-run", action="store_true", help="write nothing; print counts")
    parser.add_argument("--check", action="store_true", help="also run the residual scan")
    args = parser.parse_args(argv)

    safety.assert_disjoint(args.input, args.output)
    root = safety.resolve_root(args.output)
    mapping = parsers.load_column_map(args.columns)
    roles_map = load_roles(args.roles)

    files = parsers.discover(args.input)
    if not files:
        print(f"no .csv/.xlsx/.json files under {args.input}", file=sys.stderr)
        return 1

    messages, source_hashes = [], {}
    for path in files:
        source_hashes[path.name] = sha256_file(path)
        messages += parsers.read_any(path, mapping)

    grouped: dict[str, list] = {}
    for message in messages:
        grouped.setdefault(message.source_conversation_id or "unknown", []).append(message)

    conversation_ids = {
        src: (src if args.keep_conversation_ids else f"conv_{i:03d}")
        for i, src in enumerate(sorted(grouped), start=1)
    }

    all_entries, speaker_maps, rows_by_conversation = [], {}, {}
    counts, distinct, unmapped, unparsed = Counter(), Counter(), set(), 0
    for src, group in grouped.items():
        conversation_id = conversation_ids[src]
        rows, entries, speakers, pmap, missing, bad_ts = scrub_conversation(
            group, conversation_id,
            address_clauses=args.address_clauses,
            amount_window=args.amount_window,
            roles_map=roles_map, date_format=args.date_format, source_hashes=source_hashes,
        )
        rows_by_conversation[conversation_id] = rows
        all_entries += entries
        speaker_maps[conversation_id] = speakers
        counts.update(e.category for e in entries)
        distinct.update(pmap.counts())
        unmapped.update(missing)
        unparsed += bad_ts

    residual = residual_scan(rows_by_conversation) if args.check else None
    settings = {
        "address_clauses": args.address_clauses,
        "amount_window": args.amount_window,
        "keep_conversation_ids": args.keep_conversation_ids,
        "date_format": args.date_format,
        "roles_file": str(args.roles) if args.roles else None,
        "schema": SCHEMA,
        "version": VERSION,
    }
    summary = report.summary(
        files_read=[p.name for p in files],
        conversations={c: len(r) for c, r in rows_by_conversation.items()},
        category_counts=dict(counts), distinct_per_category=dict(distinct),
        unmapped_speakers=sorted(unmapped), unparsed_timestamps=unparsed,
        settings=settings, residual=residual,
    )

    for conversation_id, rows in rows_by_conversation.items():
        safety.write_jsonl(root, f"{conversation_id}.jsonl", rows, dry_run=args.dry_run)
    safety.write_jsonl(
        root, Path(AUDIT_DIRNAME) / AUDIT_FILENAME,
        report.audit_rows(all_entries, conversation_ids, speaker_maps), dry_run=args.dry_run,
    )
    safety.write_json(root, SUMMARY_FILENAME, summary, dry_run=args.dry_run)

    verb = "would write" if args.dry_run else "wrote"
    print(f"{len(rows_by_conversation)} conversations, {summary['message_count']} messages")
    print(f"replacements by category: {dict(counts) or 'none'}")
    if unmapped:
        print(f"speakers with no role ({len(unmapped)}): listed in {SUMMARY_FILENAME}")
    if unparsed:
        print(f"unparseable timestamps: {unparsed} (kept as timestamp_raw)")
    if residual:
        print(f"residual scan: {residual['residual_hits_by_category'] or 'clean'}")
    print(f"{verb} to {root}; audit in {AUDIT_DIRNAME}/{AUDIT_FILENAME} (contains PII)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
