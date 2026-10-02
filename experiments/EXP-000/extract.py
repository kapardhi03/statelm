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
import json
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

#: A role_map value the operator must replace. Left in extract.example.yaml so a config that
#: has not been filled in fails loudly instead of extracting under a guessed role.
ROLE_SENTINEL = "CONFIRM_BOT_OR_AGENT"

#: Temporal SQL types. A timestamp column of one of these sorts correctly in SQL; anything else
#: is text and must be cast, or SQL would order it lexically while the CSV merge orders it by
#: parsed value, and the two disagree silently.
TEMPORAL_TYPES = (
    "timestamp with time zone", "timestamp without time zone", "timestamp", "timestamptz",
    "date", "abstime",
)

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
    #: {"column": name, "text": [...], "placeholder": {kind: text}, "drop": [...]}
    kinds: dict = field(default_factory=dict)
    #: Columns that must never appear in any statement this script issues.
    exclude: tuple[str, ...] = ()

    @property
    def classified_kinds(self) -> tuple[str, ...]:
        if not self.kinds:
            return ()
        return (*self.kinds["text"], *self.kinds["placeholder"], *self.kinds["drop"])

    @property
    def kept_kinds(self) -> tuple[str, ...]:
        """Kinds that produce a CSV row: text plus the placeholder kinds, never the dropped."""
        if not self.kinds:
            return ()
        return (*self.kinds["text"], *self.kinds["placeholder"])

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
        unfilled = sorted(k for k, v in role_map.items() if v == ROLE_SENTINEL)
        if unfilled:
            raise ConfigError(
                f"{path}: role_map still has the placeholder {ROLE_SENTINEL} for "
                f"{unfilled}. Only you can say which side of the conversation that is; "
                f"replace it with one of {ROLES}.")
        bad = sorted({v for v in role_map.values() if v not in ROLES})
        if bad:
            raise ConfigError(f"{path}: role_map values must be one of {ROLES}; got {bad}")

        kinds = _load_kinds(path, i, entry.get("kinds"))
        exclude = tuple(str(c) for c in (entry.get("exclude") or []))
        _check_exclusions(path, i, mapping, kinds, exclude)
        sources.append(Source(schema=schema or "public", table=name, columns=mapping,
                              role_map=role_map, kinds=kinds, exclude=exclude))
    if not sources:
        raise ConfigError(f"{path}: 'sources' is empty")
    return sources


def _load_kinds(path, index: int, raw) -> dict:
    """Parse the optional `kinds:` block, which decides each message kind's disposition.

    Three dispositions, and every kind seen in the data must have one: `text` keeps the body,
    `placeholder` replaces it with a fixed string, `drop` removes the row. A kind the config
    does not classify fails the run rather than being guessed at, because an unclassified kind
    may carry content nobody has decided about.
    """
    if raw is None:
        return {}
    if not isinstance(raw, dict) or "column" not in raw:
        raise ConfigError(f"{path}: sources[{index}].kinds needs a 'column'")
    text = [str(k) for k in (raw.get("text") or [])]
    placeholder = {str(k): str(v) for k, v in (raw.get("placeholder") or {}).items()}
    drop = [str(k) for k in (raw.get("drop") or [])]
    if not text and not placeholder:
        raise ConfigError(
            f"{path}: sources[{index}].kinds classifies no kind as text or placeholder, "
            "so the extract would produce no rows")
    overlap = (set(text) & set(placeholder)) | (set(text) & set(drop)) | (set(placeholder) & set(drop))
    if overlap:
        raise ConfigError(
            f"{path}: sources[{index}].kinds gives {sorted(overlap)} more than one disposition")
    empty = sorted(k for k, v in placeholder.items() if not v.strip())
    if empty:
        raise ConfigError(
            f"{path}: sources[{index}].kinds has an empty placeholder for {empty}; an empty "
            "string would be indistinguishable from a missing message")
    return {"column": str(raw["column"]), "text": text, "placeholder": placeholder, "drop": drop}


def _check_exclusions(path, index: int, mapping: dict, kinds: dict, exclude) -> None:
    """A column cannot be both excluded and used. Catches `text: intent` and similar."""
    excluded = {c.lower() for c in exclude}
    clashes = sorted(f"{field}: {column}" for field, column in mapping.items()
                     if column.lower() in excluded)
    if kinds and kinds["column"].lower() in excluded:
        clashes.append(f"kinds.column: {kinds['column']}")
    if clashes:
        raise ConfigError(
            f"{path}: sources[{index}] both excludes and uses {clashes}. Excluding a column "
            "means it never reaches a statement, so it cannot also be mapped.")


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
    if source.kinds:
        wanted = source.kinds["column"]
        if wanted.lower() not in actual:
            raise ConfigError(
                f"{source.qualified}: kinds.column {wanted!r} does not exist; "
                f"available: {sorted(actual.values())}")
        resolved["kind"] = actual[wanted.lower()]
    if missing:
        raise ConfigError(
            f"{source.qualified}: mapped column(s) {sorted(missing)} do not exist; "
            f"available: {sorted(actual.values())}"
        )
    return resolved


def column_types(source: Source, catalog: dict) -> dict[str, str]:
    """{column name lowered: sql type} for the source's table, from the catalog."""
    return {name.lower(): kind for name, kind in catalog[(source.schema, source.table)]}


def timestamp_expression(source: Source, columns: dict, catalog: dict) -> str:
    """The ORDER BY / min / max expression for the timestamp column.

    A temporal column sorts correctly as itself. A text column must be cast, because SQL would
    otherwise order it lexically while `write_csv` merges the streams by parsed ISO value, and
    `heapq.merge` assumes each stream is already sorted by the merge key. The two disagreeing
    produces a silently misordered CSV, and `turn_index` downstream comes from that order.
    """
    quoted = quote_ident(columns["timestamp"])
    declared = column_types(source, catalog).get(columns["timestamp"].lower(), "").lower()
    if any(declared.startswith(temporal) for temporal in TEMPORAL_TYPES):
        return quoted
    return f"({quoted})::timestamptz"


# --------------------------------------------------------------------------- extract


def _row_filter(source: Source, columns, since, until, *, keep_only_wanted_kinds: bool
                ) -> tuple[str, list]:
    """The WHERE clause shared by the counting query and the extract query.

    Sharing it is the point: if the kind filter applied only to the extract, conversations would
    be *selected* on counts that include rows the extract then drops, and the
    --min-customer-messages floor would be measured against a different population than the one
    written out.
    """
    clauses, params = [], []
    if since:
        clauses.append(f"{quote_ident(columns['timestamp'])} >= %s")
        params.append(since)
    if until:
        clauses.append(f"{quote_ident(columns['timestamp'])} < %s")
        params.append(until)
    if keep_only_wanted_kinds and source.kinds:
        clauses.append(f"{quote_ident(columns['kind'])} = ANY(%s)")
        params.append(list(source.kept_kinds))
        # An empty body is a non-message for a text row, but a placeholder row legitimately
        # has none, so the check is scoped to the text kinds.
        if source.kinds["text"]:
            clauses.append(
                f"({quote_ident(columns['kind'])} <> ALL(%s) "
                f"OR btrim({quote_ident(columns['text'])}) <> '')")
            params.append(list(source.kinds["text"]))
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def conversation_counts(session, source, columns, *, since=None, until=None,
                        ts_expression=None) -> dict:
    """Per conversation: role counts, per-kind counts, eligible count, first and last timestamp.

    One aggregate query does four jobs: it feeds the sampling floor, the per-kind counts for the
    metadata file, the printed role summary, and the unclassified-kind check. Aggregates only;
    no statement here selects a message body, so nothing in this path can leak content.

    `eligible` counts only the rows that the sampling floor is defined over. For the ARTHRYX
    schema that is inbound text, which is customer-role rows of a text kind: a conversation of
    four voice notes has no labellable turns, so it must not pass a floor meant to guarantee
    four.
    """
    where, params = _row_filter(source, columns, since, until, keep_only_wanted_kinds=False)
    ts = ts_expression or quote_ident(columns["timestamp"])
    conv, role = (quote_ident(columns[k]) for k in ("conversation_id", "speaker_role"))
    group, select = [conv, role], [conv, role]
    if source.kinds:
        group.append(quote_ident(columns["kind"]))
        select.append(quote_ident(columns["kind"]))
    sql = (
        f"SELECT {', '.join(select)}, count(*), min({ts}), max({ts}) "
        f"FROM {quote_ident(source.schema)}.{quote_ident(source.table)}{where} "
        f"GROUP BY {', '.join(str(i + 1) for i in range(len(group)))}"
    )
    out: dict = {}
    with session.cursor() as cursor:
        session.select(cursor, sql, params or None)
        for row in cursor.fetchall():
            if source.kinds:
                conversation_id, role_value, kind_value, count, first, last = row
            else:
                conversation_id, role_value, count, first, last = row
                kind_value = None
            entry = out.setdefault(str(conversation_id), {
                "roles": {}, "kinds": {}, "eligible": 0, "first": None, "last": None})
            canonical = source.role_map.get(str(role_value), str(role_value))
            entry["roles"][canonical] = entry["roles"].get(canonical, 0) + int(count)
            if kind_value is not None:
                entry["kinds"][str(kind_value)] = (
                    entry["kinds"].get(str(kind_value), 0) + int(count))
            countable = (not source.kinds) or str(kind_value) in source.kinds["text"]
            if canonical == "customer" and countable:
                entry["eligible"] += int(count)
            for key, value in (("first", first), ("last", last)):
                iso, _ = timestamps.parse(value)
                if iso and (entry[key] is None or (iso < entry[key] if key == "first" else iso > entry[key])):
                    entry[key] = iso
    return out


def unclassified_kinds(source: Source, counts: dict) -> list[str]:
    """Kinds present in the data that the config gives no disposition. Never guessed at."""
    if not source.kinds:
        return []
    seen = {kind for entry in counts.values() for kind in entry["kinds"]}
    return sorted(seen - set(source.classified_kinds))


def builder_counts(session, source, column: str) -> dict[str, int]:
    """{value: row count} for a tenant column. An aggregate, not a filter.

    EXP-000's consent assumption is single-tenant. This verifies it rather than trusting it: a
    second value appearing means the assumption no longer holds, and the run says so.
    """
    quoted = quote_ident(column)
    sql = (f"SELECT {quoted}, count(*) FROM "
           f"{quote_ident(source.schema)}.{quote_ident(source.table)} GROUP BY 1")
    with session.cursor() as cursor:
        session.select(cursor, sql)
        return {("" if value is None else str(value)): int(count)
                for value, count in cursor.fetchall()}


def text_expression(source: Source, columns: dict) -> tuple[str, list]:
    """The SELECT expression for the message text, and its bound parameters.

    For a source with a `kinds` block this is a CASE that returns the body only for a text kind
    and a fixed placeholder otherwise. Doing the substitution in SQL rather than in Python is
    the whole point: the body of a media row is never transmitted to this process, so "never
    read or copy the original body for these rows" is a property of the query, not a promise
    about what the code does with the value afterwards. `media_id` and `media_mime` appear in no
    statement at all, being excluded rather than selected and discarded.

    Every kind value and placeholder string is a bound parameter; none is interpolated.
    """
    body = quote_ident(columns["text"])
    if not source.kinds:
        return body, []
    kind = quote_ident(columns["kind"])
    branches, params = [], []
    if source.kinds["text"]:
        branches.append(f"WHEN {kind} = ANY(%s) THEN {body}")
        params.append(list(source.kinds["text"]))
    for value, placeholder in sorted(source.kinds["placeholder"].items()):
        branches.append(f"WHEN {kind} = %s THEN %s")
        params.extend([value, placeholder])
    # No ELSE: the WHERE already restricts kind to the kept set, so an unreachable branch would
    # yield NULL, and `_message_rows` fails on an empty text rather than writing a blank row.
    return f"CASE {' '.join(branches)} END", params


def choose_conversations(counts: dict, *, n: int, seed: int, min_customer_messages: int) -> list[str]:
    """Filter then sample, in Python so the same seed gives the same conversations.

    SQL `ORDER BY random()` would not be reproducible across servers or runs, which matters
    because EXP-000's pilot items must be identifiable later and excluded from the test split.
    """
    eligible = sorted(
        cid for cid, entry in counts.items()
        if entry.get("eligible", entry["roles"].get("customer", 0)) >= min_customer_messages
    )
    if n >= len(eligible):
        return eligible
    return sorted(random.Random(seed).sample(eligible, n))


def _message_rows(session, source, columns, conversation_ids, *, since=None, until=None,
                  ts_expression=None, stats=None):
    """Yield (conversation_id, speaker, role, iso_timestamp, text) ordered by conversation, time.

    A generator over a server-side cursor: rows are handed to the CSV writer one at a time and
    never collected, so message text has no resting place in this process.

    Two failures are refused rather than written. A timestamp that does not parse would sort to
    the front as an empty string and silently reorder a conversation, and `turn_index` in the
    annotation items comes straight from this order. And a stream that is not non-decreasing in
    the merge key means the SQL ordering and the Python merge key disagree, which `heapq.merge`
    cannot detect and which corrupts the output rather than erroring.
    """
    where, params = _row_filter(source, columns, since, until, keep_only_wanted_kinds=True)
    joiner = " AND " if where else " WHERE "
    conv, speaker, role = (
        quote_ident(columns[k]) for k in ("conversation_id", "speaker", "speaker_role"))
    ts = ts_expression or quote_ident(columns["timestamp"])
    text_sql, text_params = text_expression(source, columns)
    sql = (
        f"SELECT {conv}, {speaker}, {role}, {quote_ident(columns['timestamp'])}, {text_sql} "
        f"FROM {quote_ident(source.schema)}.{quote_ident(source.table)}"
        f"{where}{joiner}{conv} = ANY(%s) "
        f"ORDER BY {conv}, {ts}"
    )
    previous = None
    with session.cursor() as cursor:
        # Parameter order follows the statement text, not the order the clauses were built:
        # the CASE lives in the SELECT list, which precedes the WHERE. Getting this backwards
        # binds the WHERE's kind list into the CASE, which the test shim's strict
        # placeholder/parameter pairing is what caught.
        session.select(cursor, sql, [*text_params, *params, list(conversation_ids)])
        for conversation_id, speaker, role_value, raw_ts, text_value in cursor:
            iso, raw = timestamps.parse(raw_ts)
            if not iso:
                raise ConfigError(
                    f"{source.qualified}: a {columns['timestamp']} value does not parse as a "
                    f"timestamp ({raw!r}). Ordering would put it first and silently reorder its "
                    "conversation, so the run stops here rather than writing a misordered CSV.")
            if text_value is None or not str(text_value).strip():
                raise ConfigError(
                    f"{source.qualified}: a kept row produced no text. Every kind in "
                    f"{source.kept_kinds} must map to the body or a placeholder.")
            key = (str(conversation_id), iso)
            if previous is not None and key < previous:
                raise ConfigError(
                    f"{source.qualified}: rows arrived out of order ({previous} then {key}). "
                    "The SQL ordering and the parsed merge key disagree; the CSV would be "
                    "misordered. Check the timestamp column's type.")
            previous = key
            if stats is not None and source.kinds:
                placeholders = set(source.kinds["placeholder"].values())
                if str(text_value) in placeholders:
                    stats["placeholders"][str(text_value)] = (
                        stats["placeholders"].get(str(text_value), 0) + 1)
            yield (
                str(conversation_id),
                "" if speaker is None else str(speaker),
                source.role_map.get(str(role_value), str(role_value)),
                iso,
                str(text_value),
            )


def write_csv(session, sources, resolved, conversation_ids, output: Path, *, since=None,
              until=None, ts_expressions=None) -> dict:
    """Stream every source into one CSV, globally ordered, and return counts only."""
    stats = {"messages": 0, "roles": {}, "conversations": set(), "first": None, "last": None,
             "placeholders": {}}
    streams = [
        _message_rows(session, source, resolved[i], conversation_ids, since=since, until=until,
                      ts_expression=(ts_expressions or {}).get(i), stats=stats)
        for i, source in enumerate(sources)
    ]
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


def write_metadata(output: Path, payload: dict, *, allowed_root: Path | None = None) -> Path:
    """Counts and settings beside the CSV. No message text, no row values.

    It lands in data/raw/ because that is the one tree this script is allowed to write, and it
    is gitignored with the CSV it describes. Everything in it is an aggregate, so it is safe to
    copy into runs/EXP-000/ as it stands.
    """
    path = dbsafety.assert_in_data_raw(
        output.with_suffix(".meta.json"), allowed_root=allowed_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def run_extract(session, args, *, allowed_root: Path | None = None, out=sys.stdout) -> dict:
    sources = load_config(args.config)
    wanted = tuple(args.schema) if args.schema else tuple({s.schema for s in sources})
    catalog = list_columns(session, schemas=wanted)
    resolved = [resolve_source(source, catalog) for source in sources]
    ts_expressions = {i: timestamp_expression(source, resolved[i], catalog)
                      for i, source in enumerate(sources)}

    counts: dict = {}
    per_kind: dict = {}
    for i, (source, columns) in enumerate(zip(sources, resolved)):
        source_counts = conversation_counts(
            session, source, columns, since=args.since, until=args.until,
            ts_expression=ts_expressions[i])
        unclassified = unclassified_kinds(source, source_counts)
        if unclassified:
            raise ConfigError(
                f"{source.qualified}: the data contains kind(s) {unclassified} that "
                f"{args.config} does not classify. A kind with no disposition may carry "
                "content nobody has decided about, so the run stops. Add each one to "
                "kinds.text, kinds.placeholder or kinds.drop.")
        for cid, entry in source_counts.items():
            if cid in counts:
                for role, n in entry["roles"].items():
                    counts[cid]["roles"][role] = counts[cid]["roles"].get(role, 0) + n
                counts[cid]["eligible"] += entry["eligible"]
            else:
                counts[cid] = entry
            for kind, n in entry["kinds"].items():
                per_kind[kind] = per_kind.get(kind, 0) + n

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
                      since=args.since, until=args.until, ts_expressions=ts_expressions)

    tenants = {}
    if args.tenant_column:
        for source in sources:
            tenants = {**tenants, **builder_counts(session, source, args.tenant_column)}

    primary = sources[0]
    metadata = {
        "tool": "EXP-000 extract.py",
        "sources": [source.qualified for source in sources],
        "seed": args.seed,
        "conversations_considered": len(counts),
        "conversations_sampled": len(chosen),
        "conversations_written": stats["conversations"],
        "messages_written": stats["messages"],
        "per_role": stats["roles"],
        "date_range": {"first": stats["first"], "last": stats["last"]},
        "rows_by_kind_before_filtering": per_kind,
        "kind_disposition": {
            **{k: "body" for k in primary.kinds.get("text", ())},
            **{k: v for k, v in primary.kinds.get("placeholder", {}).items()},
            **{k: "dropped" for k in primary.kinds.get("drop", ())},
        },
        "placeholder_rows_written": stats["placeholders"],
        "placeholder_rows_total": sum(stats["placeholders"].values()),
        "rows_dropped_by_kind": {k: per_kind.get(k, 0) for k in primary.kinds.get("drop", ())},
        "excluded_columns": list(primary.exclude),
        "role_map": primary.role_map,
        "role_note": args.role_note or None,
        "eligibility": {
            "rule": "customer-role rows of a text kind",
            "min_customer_messages": args.min_customer_messages,
            "conversations_eligible": sum(
                1 for entry in counts.values()
                if entry.get("eligible", 0) >= args.min_customer_messages),
        },
        "timestamp": {
            "column": resolved[0]["timestamp"],
            "declared_type": column_types(primary, catalog).get(
                resolved[0]["timestamp"].lower()),
            "order_expression": ts_expressions[0],
            "unparseable_values": 0,
        },
        "tenant": ({"column": args.tenant_column, "values": tenants,
                    "single_tenant": len(tenants) <= 1} if args.tenant_column else None),
    }
    metadata_path = write_metadata(output, metadata, allowed_root=allowed_root)

    print(f"conversations: {stats['conversations']} (sampled {len(chosen)} of "
          f"{len(counts)} considered, seed {args.seed})", file=out)
    print(f"messages: {stats['messages']}", file=out)
    print(f"per role: {stats['roles']}", file=out)
    if stats["placeholders"]:
        print(f"placeholder rows: {stats['placeholders']} "
              f"(total {sum(stats['placeholders'].values())})", file=out)
    if primary.kinds.get("drop"):
        print(f"dropped kinds: {metadata['rows_dropped_by_kind']}", file=out)
    if args.tenant_column:
        print(f"{args.tenant_column}: {tenants}"
              f"{'' if len(tenants) <= 1 else '  <- MORE THAN ONE TENANT'}", file=out)
        if len(tenants) > 1:
            raise ConfigError(
                f"{args.tenant_column} has {len(tenants)} distinct values {sorted(tenants)}, "
                "but EXP-000's consent assumption is single-tenant. The CSV has been written; "
                "check consent before using it, or add a tenant filter.")
    print(f"date range: {stats['first'] or 'n/a'} to {stats['last'] or 'n/a'}", file=out)
    print(f"wrote {output}", file=out)
    print(f"wrote {metadata_path} (counts only)", file=out)
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
    parser.add_argument("--tenant-column", default=None, metavar="COLUMN",
                        help="record this column's distinct values in the metadata and refuse "
                             "more than one. A check on the single-tenant consent assumption, "
                             "not a filter")
    parser.add_argument("--role-note", default=None,
                        help="a sentence recorded verbatim in the metadata, for a role mapping "
                             "the schema cannot fully justify")
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
