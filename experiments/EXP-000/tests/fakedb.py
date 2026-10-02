"""An in-memory SQLite stand-in for the ARTHRYX database, with invented data.

Real SQL runs against it, so the grouping, filtering and ordering in `extract.py` are genuinely
exercised rather than mocked. A thin shim serves `information_schema.columns` from SQLite's own
schema and rewrites the two PostgreSQL-isms the extractor uses (`%s` placeholders and
`= ANY(%s)`).

Every value here is invented. No client data appears in this repo.
"""

from __future__ import annotations

import re
import sqlite3

import dbsafety

#: Invented messages. Distinctive text so a test can assert it never reaches stdout.
MESSAGES = [
    # conversation, sender, sender_type, created_at, body
    ("ARTH-1", "Asha Rao", "user", "2025-08-12T10:00:00", "ZEBRAFISH looking for a 3BHK"),
    ("ARTH-1", "Desk", "staff", "2025-08-12T10:01:00", "QUASAR happy to help"),
    ("ARTH-1", "Asha Rao", "user", "2025-08-12T10:02:00", "ZEBRAFISH budget around 40 lakhs"),
    ("ARTH-1", "Bot", "automation", "2025-08-12T10:03:00", "PANGOLIN automated reply"),
    ("ARTH-1", "Asha Rao", "user", "2025-08-12T10:04:00", "ZEBRAFISH maybe 45"),
    ("ARTH-1", "Asha Rao", "user", "2025-08-12T10:05:00", "ZEBRAFISH call me on 9876543210"),
    # four customer messages exactly: on the boundary of --min-customer-messages 4
    ("ARTH-2", "Vikram Nair", "user", "2025-09-01T09:00:00", "NARWHAL need a plot"),
    ("ARTH-2", "Desk", "staff", "2025-09-01T09:01:00", "QUASAR sure"),
    ("ARTH-2", "Vikram Nair", "user", "2025-09-01T09:02:00", "NARWHAL in Gachibowli"),
    ("ARTH-2", "Vikram Nair", "user", "2025-09-01T09:03:00", "NARWHAL under 1 crore"),
    ("ARTH-2", "Vikram Nair", "user", "2025-09-01T09:04:00", "NARWHAL thanks"),
    # one customer message: must be filtered out by the default threshold
    ("ARTH-3", "Meera Iyer", "user", "2025-09-02T08:00:00", "OCELOT just browsing"),
    # five customer messages, but later than the others, for the date filters
    ("ARTH-4", "Dev Shah", "user", "2025-10-05T12:00:00", "AXOLOTL villa enquiry"),
    ("ARTH-4", "Dev Shah", "user", "2025-10-05T12:01:00", "AXOLOTL two parking slots"),
    ("ARTH-4", "Dev Shah", "user", "2025-10-05T12:02:00", "AXOLOTL budget 2 crore"),
    ("ARTH-4", "Dev Shah", "user", "2025-10-05T12:03:00", "AXOLOTL any discount"),
    ("ARTH-4", "Desk", "staff", "2025-10-05T12:04:00", "QUASAR checking"),
    ("ARTH-4", "Dev Shah", "user", "2025-10-05T12:05:00", "AXOLOTL ok"),
]

#: Invented rows in an unrelated table, which the inspect heuristic should skip.
INVOICES = [(1, "INV-001", 25000), (2, "INV-002", 48000)]

SECRET_TEXTS = {m[4].split()[0] for m in MESSAGES} | {"INV-001", "INV-002"}

_ANY = re.compile(r"=\s*ANY\(%s\)", re.I)
_SCHEMA_QUALIFIER = re.compile(r'"[A-Za-z_][A-Za-z0-9_]*"\.(?=")')


class FakeCursor:
    def __init__(self, connection) -> None:
        self._connection = connection
        self._cursor = connection.raw.cursor()
        self._rows: list | None = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=None):
        self._connection.statements.append((sql, params))
        if sql.strip() == dbsafety.READ_ONLY_STATEMENT:
            self._connection.read_only_set = True
            self._rows = []
            return self
        if "information_schema.columns" in sql:
            self._rows = self._connection.catalog_rows()
            return self
        self._rows = None
        translated, values = self._translate(sql, params)
        self._cursor.execute(translated, values)
        return self

    def _translate(self, sql, params):
        # SQLite has no schemas, so strip the qualifier. Against PostgreSQL the extractor's
        # "public"."messages" is correct; this is a shim detail, not a product difference.
        sql = _SCHEMA_QUALIFIER.sub("", sql)
        values = list(params or [])
        match = _ANY.search(sql)
        if match:
            # The id list is always the last parameter the extractor passes.
            ids = values.pop()
            sql = sql[: match.start()] + "IN (" + ",".join("?" * len(ids)) + ")" + sql[match.end():]
            values = values + list(ids)
        return sql.replace("%s", "?"), values

    def fetchall(self):
        return list(self._rows) if self._rows is not None else self._cursor.fetchall()

    def fetchone(self):
        if self._rows is not None:
            return self._rows[0] if self._rows else None
        return self._cursor.fetchone()

    def __iter__(self):
        return iter(self.fetchall())


class FakeConnection:
    """Minimal DB-API surface, plus a record of every statement executed."""

    def __init__(self, *, messages=None, with_invoices: bool = True) -> None:
        self.raw = sqlite3.connect(":memory:")
        self.statements: list[tuple] = []
        self.read_only = False
        self.read_only_set = False
        self.raw.execute(
            "CREATE TABLE messages (conversation_id TEXT, sender_name TEXT, "
            "sender_type TEXT, created_at TEXT, body TEXT)"
        )
        self.raw.executemany(
            "INSERT INTO messages VALUES (?,?,?,?,?)",
            MESSAGES if messages is None else messages,
        )
        if with_invoices:
            self.raw.execute("CREATE TABLE invoices (id INTEGER, number TEXT, amount INTEGER)")
            self.raw.executemany("INSERT INTO invoices VALUES (?,?,?)", INVOICES)
        self.raw.commit()

    def cursor(self, *args, **kwargs):
        return FakeCursor(self)

    def catalog_rows(self):
        rows = []
        for (table,) in self.raw.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall():
            for info in self.raw.execute(f'PRAGMA table_info("{table}")').fetchall():
                rows.append(("public", table, info[1], info[2].lower() or "text"))
        return rows

    @property
    def data_statements(self):
        """Everything except the read-only statement."""
        return [s for s, _ in self.statements if s.strip() != dbsafety.READ_ONLY_STATEMENT]


def connect_fn(url):
    """Signature-compatible with psycopg.connect. Ignores the URL, as a fake should."""
    return FakeConnection()
