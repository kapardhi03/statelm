#!/usr/bin/env python3
"""EXP-000 conversation extractor. Runs locally on Kapardhi's machine.

Claude never connects to this database and never sees message content. Two modes:

    python extract.py --inspect
    python extract.py --extract --config extract.yaml

`--inspect` prints structure only: table, column, type, row count. It cannot print a row value,
because in that mode no statement selects a column from a user table — only `information_schema`
and `count(*)`.

`--extract` writes `data/raw/arthryx_messages.csv` with exactly five columns, one row per
message, ordered by conversation_id then timestamp, and prints counts to the terminal.

Credentials come from DATABASE_URL and nowhere else. See README.md for the read-only user.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

import dbsafety
import timestamps

CSV_COLUMNS = ("conversation_id", "speaker", "speaker_role", "timestamp", "text")
CANONICAL_FIELDS = ("conversation_id", "speaker", "speaker_role", "timestamp", "text")
DEFAULT_OUTPUT = "arthryx_messages.csv"
ROLES = ("bot", "agent", "customer")

#: A table is a candidate when its name looks conversational, or when its columns do.
_TABLE_HINTS = ("message", "messages", "msg", "conversation", "conversations", "chat", "chats",
                "thread", "threads", "dialog", "dialogue", "transcript", "utterance")
_TEXT_HINTS = ("text", "body", "message", "content", "utterance")
_TIME_HINTS = ("timestamp", "created_at", "sent_at", "time", "ts", "created")
_WHO_HINTS = ("speaker", "sender", "author", "from", "role", "direction", "user_id")


class ConfigError(Exception):
    pass


def quote_ident(name: str) -> str:
    """Quote an identifier for PostgreSQL.

    Only ever called with a name the catalog itself reported, so the value is known to exist and
    did not come from the config as free text. Doubling embedded quotes is the complete rule.
    """
    return '"' + name.replace('"', '""') + '"'


# --------------------------------------------------------------------------- catalog


SYSTEM_SCHEMAS = ("pg_catalog", "information_schema")


def list_schemas(session) -> list[str]:
    """Every non-system schema this connection can see."""
    sql = (
        "SELECT schema_name FROM information_schema.schemata "
        "WHERE schema_name <> ALL(%s) "
        "AND schema_name NOT LIKE 'pg_toast%%' AND schema_name NOT LIKE 'pg_temp%%' "
        "ORDER BY schema_name"
    )
    with session.cursor() as cursor:
        session.select(cursor, sql, (list(SYSTEM_SCHEMAS),))
        return [row[0] for row in cursor.fetchall()]


def connection_identity(session) -> tuple[str, str]:
    """(database, role). Two scalars, no table data."""
    with session.cursor() as cursor:
        session.select(cursor, "SELECT current_database(), current_user")
        database, role = cursor.fetchone()
        return str(database), str(role)


def list_columns(session, *, schemas=("public",)) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """{(schema, table): [(column, type), ...]} for ordinary tables and views."""
    sql = (
        "SELECT c.table_schema, c.table_name, c.column_name, c.data_type "
        "FROM information_schema.columns c "
        "JOIN information_schema.tables t "
        "  ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
        "WHERE c.table_schema = ANY(%s) AND t.table_type IN ('BASE TABLE', 'VIEW') "
        "ORDER BY c.table_schema, c.table_name, c.ordinal_position"
    )
    out: dict[tuple[str, str], list[tuple[str, str]]] = {}
    with session.cursor() as cursor:
        session.select(cursor, sql, (list(schemas),))
        for schema, table, column, data_type in cursor.fetchall():
            out.setdefault((schema, table), []).append((column, data_type))
    return out


def row_count(session, schema: str, table: str) -> int:
    """count(*) only. Returns an aggregate, never a row value."""
    sql = f"SELECT count(*) FROM {quote_ident(schema)}.{quote_ident(table)}"
    with session.cursor() as cursor:
        session.select(cursor, sql)
        return int(cursor.fetchone()[0])


def looks_conversational(table: str, columns: list[tuple[str, str]]) -> bool:
    names = {c.lower() for c, _ in columns}
    if any(hint in table.lower() for hint in _TABLE_HINTS):
        return True
    has = lambda hints: any(any(h in n for h in hints) for n in names)
    return has(_TEXT_HINTS) and has(_TIME_HINTS) and has(_WHO_HINTS)


def run_inspect(session, *, all_tables: bool = False, schemas=None,
                out=sys.stdout) -> list[tuple[str, str]]:
    """Print structure for candidate tables. Returns the candidates, for tests."""
    searched = list(schemas) if schemas else list_schemas(session)
    catalog = list_columns(session, schemas=tuple(searched)) if searched else {}
    candidates = [
        key for key, columns in catalog.items()
        if all_tables or looks_conversational(key[1], columns)
    ]
    print("Structure only. No row values are read in this mode.\n", file=out)
    if not catalog:
        # Nothing is visible at all, so --all-tables would not help. Say what was actually
        # looked at and what usually explains it.
        database, role = connection_identity(session)
        print("No tables are visible to this connection.", file=out)
        print(f"    database:         {database}", file=out)
        print(f"    role:             {role}", file=out)
        print(f"    schemas searched: {', '.join(searched) or '(none visible)'}", file=out)
        print(file=out)
        print("That usually means one of:", file=out)
        print("  - the role lacks privileges: GRANT USAGE ON SCHEMA <s> and "
              "GRANT SELECT ON ALL TABLES IN SCHEMA <s>", file=out)
        print("  - the tables are in another schema: try --schema <name>", file=out)
        print("  - the tables are in another database: check the name in DATABASE_URL", file=out)
        return []
    if not candidates:
        print(f"{len(catalog)} table(s) visible, none of which looked conversational. "
              f"Re-run with --all-tables to list them all.", file=out)
        return []
    for schema, table in sorted(candidates):
        print(f"{schema}.{table}  ({row_count(session, schema, table)} rows)", file=out)
        for column, data_type in catalog[(schema, table)]:
            print(f"    {column:<28} {data_type}", file=out)
        print(file=out)
    print("Paste this into the Claude session to have the extract.yaml mapping written.", file=out)
    return sorted(candidates)


# --------------------------------------------------------------------------- config


@dataclass(frozen=True)
class Source:
    schema: str
    table: str
    columns: dict[str, str]
    role_map: dict[str, str] = field(default_factory=dict)

    @property
    def qualified(self) -> str:
        return f"{self.schema}.{self.table}"


def load_config(path: str | Path) -> list[Source]:
    """Parse extract.yaml. Every mapped field must be present; nothing is inferred."""
    import yaml

    raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict) or "sources" not in raw:
        raise ConfigError(f"{path}: expected a top-level 'sources:' list")
    sources = []
    for i, entry in enumerate(raw["sources"]):
        if not isinstance(entry, dict) or "table" not in entry or "columns" not in entry:
            raise ConfigError(f"{path}: sources[{i}] needs 'table' and 'columns'")
        table = str(entry["table"])
        schema, _, name = table.rpartition(".")
        mapping = {str(k): str(v) for k, v in (entry["columns"] or {}).items()}
        missing = [f for f in CANONICAL_FIELDS if f not in mapping]
        if missing:
            raise ConfigError(f"{path}: sources[{i}] is missing column mapping(s) {missing}")
        unknown = set(mapping) - set(CANONICAL_FIELDS)
        if unknown:
            raise ConfigError(f"{path}: sources[{i}] has unknown field(s) {sorted(unknown)}")
        role_map = {str(k): str(v) for k, v in (entry.get("role_map") or {}).items()}
        bad = sorted({v for v in role_map.values() if v not in ROLES})
        if bad:
            raise ConfigError(f"{path}: role_map values must be one of {ROLES}; got {bad}")
        sources.append(Source(schema=schema or "public", table=name,
                              columns=mapping, role_map=role_map))
    if not sources:
        raise ConfigError(f"{path}: 'sources' is empty")
    return sources


def resolve_source(source: Source, catalog: dict) -> dict[str, str]:
    """Check the table and every mapped column against the catalog.

    Returns canonical column names taken from the catalog, so the SQL is built from names the
    database reported rather than from strings in the config. A mapped column that does not
    exist is an error naming it, never a guess at a similar one.
    """
    key = (source.schema, source.table)
    if key not in catalog:
        available = sorted(f"{s}.{t}" for s, t in catalog)[:12]
        raise ConfigError(f"table {source.qualified!r} does not exist; saw {available}")
    actual = {c.lower(): c for c, _ in catalog[key]}
    resolved, missing = {}, []
    for canonical, column in source.columns.items():
        if column.lower() in actual:
            resolved[canonical] = actual[column.lower()]
        else:
            missing.append(column)
    if missing:
        raise ConfigError(
            f"{source.qualified}: mapped column(s) {sorted(missing)} do not exist; "
            f"available: {sorted(actual.values())}"
        )
    return resolved


# --------------------------------------------------------------------------- extract


def _time_filter(columns, since, until) -> tuple[str, list]:
    clauses, params = [], []
    if since:
        clauses.append(f"{quote_ident(columns['timestamp'])} >= %s")
        params.append(since)
    if until:
        clauses.append(f"{quote_ident(columns['timestamp'])} < %s")
        params.append(until)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def conversation_counts(session, source, columns, *, since=None, until=None) -> dict:
    """Per conversation: {role_value: count} plus first and last timestamp.

    Aggregates only. No message text is selected, so nothing here can leak content.
    """
    where, params = _time_filter(columns, since, until)
    conv, role, ts = (quote_ident(columns[k]) for k in ("conversation_id", "speaker_role", "timestamp"))
    sql = (
        f"SELECT {conv}, {role}, count(*), min({ts}), max({ts}) "
        f"FROM {quote_ident(source.schema)}.{quote_ident(source.table)}{where} "
        f"GROUP BY 1, 2"
    )
    out: dict = {}
    with session.cursor() as cursor:
        session.select(cursor, sql, params or None)
        for conversation_id, role_value, count, first, last in cursor.fetchall():
            entry = out.setdefault(str(conversation_id), {"roles": {}, "first": None, "last": None})
            canonical = source.role_map.get(str(role_value), str(role_value))
            entry["roles"][canonical] = entry["roles"].get(canonical, 0) + int(count)
            for key, value in (("first", first), ("last", last)):
                iso, _ = timestamps.parse(value)
                if iso and (entry[key] is None or (iso < entry[key] if key == "first" else iso > entry[key])):
                    entry[key] = iso
    return out


def choose_conversations(counts: dict, *, n: int, seed: int, min_customer_messages: int) -> list[str]:
    """Filter then sample, in Python so the same seed gives the same conversations.

    SQL `ORDER BY random()` would not be reproducible across servers or runs, which matters
    because EXP-000's pilot items must be identifiable later and excluded from the test split.
    """
    eligible = sorted(
        cid for cid, entry in counts.items()
        if entry["roles"].get("customer", 0) >= min_customer_messages
    )
    if n >= len(eligible):
        return eligible
    return sorted(random.Random(seed).sample(eligible, n))


def _message_rows(session, source, columns, conversation_ids, *, since=None, until=None):
    """Yield (conversation_id, speaker, role, iso_timestamp, text) ordered by conversation, time.

    A generator over a server-side cursor: rows are handed to the CSV writer one at a time and
    never collected, so message text has no resting place in this process.
    """
    where, params = _time_filter(columns, since, until)
    joiner = " AND " if where else " WHERE "
    conv, speaker, role, ts, text = (
        quote_ident(columns[k])
        for k in ("conversation_id", "speaker", "speaker_role", "timestamp", "text")
    )
    sql = (
        f"SELECT {conv}, {speaker}, {role}, {ts}, {text} "
        f"FROM {quote_ident(source.schema)}.{quote_ident(source.table)}"
        f"{where}{joiner}{conv} = ANY(%s) "
        f"ORDER BY {conv}, {ts}"
    )
    with session.cursor() as cursor:
        session.select(cursor, sql, [*params, list(conversation_ids)])
        for conversation_id, speaker, role_value, raw_ts, text_value in cursor:
            iso, _ = timestamps.parse(raw_ts)
            yield (
                str(conversation_id),
                "" if speaker is None else str(speaker),
                source.role_map.get(str(role_value), str(role_value)),
                iso or "",
                "" if text_value is None else str(text_value),
            )


def write_csv(session, sources, resolved, conversation_ids, output: Path, *, since=None, until=None) -> dict:
    """Stream every source into one CSV, globally ordered, and return counts only."""
    streams = [
        _message_rows(session, source, resolved[i], conversation_ids, since=since, until=until)
        for i, source in enumerate(sources)
    ]
    stats = {"messages": 0, "roles": {}, "conversations": set(), "first": None, "last": None}
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(CSV_COLUMNS)
        for row in heapq.merge(*streams, key=lambda r: (r[0], r[3])):
            writer.writerow(row)
            stats["messages"] += 1
            stats["conversations"].add(row[0])
            stats["roles"][row[2]] = stats["roles"].get(row[2], 0) + 1
            if row[3]:
                stats["first"] = min(stats["first"] or row[3], row[3])
                stats["last"] = max(stats["last"] or row[3], row[3])
    stats["conversations"] = len(stats["conversations"])
    return stats


def run_extract(session, args, *, allowed_root: Path | None = None, out=sys.stdout) -> dict:
    sources = load_config(args.config)
    wanted = tuple(args.schema) if args.schema else tuple({s.schema for s in sources})
    catalog = list_columns(session, schemas=wanted)
    resolved = [resolve_source(source, catalog) for source in sources]

    counts: dict = {}
    for source, columns in zip(sources, resolved):
        for cid, entry in conversation_counts(
            session, source, columns, since=args.since, until=args.until
        ).items():
            if cid in counts:
                for role, n in entry["roles"].items():
                    counts[cid]["roles"][role] = counts[cid]["roles"].get(role, 0) + n
            else:
                counts[cid] = entry

    chosen = choose_conversations(
        counts, n=args.n_conversations, seed=args.seed,
        min_customer_messages=args.min_customer_messages,
    )
    if not chosen:
        raise ConfigError(
            f"no conversation has at least {args.min_customer_messages} customer messages "
            f"after the date filters; {len(counts)} conversations were considered"
        )

    output = dbsafety.assert_in_data_raw(args.output, allowed_root=allowed_root)
    stats = write_csv(session, sources, resolved, chosen, output,
                      since=args.since, until=args.until)

    print(f"conversations: {stats['conversations']} (sampled {len(chosen)} of "
          f"{len(counts)} considered, seed {args.seed})", file=out)
    print(f"messages: {stats['messages']}", file=out)
    print(f"per role: {stats['roles']}", file=out)
    print(f"date range: {stats['first'] or 'n/a'} to {stats['last'] or 'n/a'}", file=out)
    print(f"wrote {output}", file=out)
    print("Counts only above. No message text is printed, logged or kept outside the CSV.", file=out)
    return stats


# --------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="EXP-000 conversation extractor (run locally)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--inspect", action="store_true", help="print structure only, never values")
    mode.add_argument("--extract", action="store_true", help="write the CSV")
    parser.add_argument("--config", type=Path, help="extract.yaml (required with --extract)")
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUTPUT),
                        help="relative to data/raw/; anywhere else is refused")
    parser.add_argument("--n-conversations", type=int, default=100)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--min-customer-messages", type=int, default=4)
    parser.add_argument("--since", default=None, help="inclusive lower bound on timestamp")
    parser.add_argument("--until", default=None, help="exclusive upper bound on timestamp")
    parser.add_argument("--all-tables", action="store_true",
                        help="with --inspect, show every table, not only conversational ones")
    parser.add_argument("--schema", action="append", default=None, metavar="NAME",
                        help="schema to search; repeatable. Default: all non-system schemas")
    return parser


def main(argv=None, *, connect_fn=None, allowed_root=None, out=sys.stdout) -> int:
    args = build_parser().parse_args(argv)
    if args.extract and not args.config:
        print("--extract needs --config extract.yaml", file=sys.stderr)
        return 2
    session = dbsafety.connect(connect_fn)
    if args.inspect:
        run_inspect(session, all_tables=args.all_tables, schemas=args.schema, out=out)
    else:
        run_extract(session, args, allowed_root=allowed_root, out=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
