"""Connection and SQL discipline for `extract.py`.

Three things live here because each is a promise the extractor makes and each is easier to
enforce in one place than to remember at every call site:

1. Credentials come from `DATABASE_URL` and nowhere else. No file in the repo is consulted,
   nothing is hardcoded, and the URL is never returned, printed or recorded.
2. The session is put in read-only mode before any other statement runs.
3. Only SELECT (or WITH ... SELECT) reaches the database after that.

`connect` takes a `connect_fn` so tests can pass a fake connection. The default is psycopg,
imported lazily so neither the tests nor `--help` need a driver installed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

READ_ONLY_STATEMENT = "SET default_transaction_read_only = on"
_SELECT = re.compile(r"^\s*(?:with\b.*?\bselect\b|select\b)", re.I | re.S)

CREDENTIAL_ENV = "DATABASE_URL"


class MissingCredentials(Exception):
    pass


class NotReadOnly(Exception):
    pass


class NotASelect(Exception):
    pass


class OutsideDataRaw(Exception):
    pass


def database_url() -> str:
    """The connection string, from the environment only.

    Deliberately does not fall back to a config file, a dotenv, or a default DSN: a credential
    that can come from the repo is a credential that can be committed.
    """
    url = os.environ.get(CREDENTIAL_ENV, "").strip()
    if not url:
        raise MissingCredentials(
            f"{CREDENTIAL_ENV} is not set. Export it for this shell only, ideally for a "
            f"read-only database user. extract.py reads credentials from nowhere else."
        )
    return url


def assert_select_only(statement: str) -> str:
    """Gate every data statement. Raises rather than returning False, so a slip cannot pass."""
    if not _SELECT.match(statement):
        raise NotASelect(f"extract.py issues only SELECT statements; refused: {statement[:60]!r}")
    return statement


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_raw_root(root: Path | None = None) -> Path:
    return ((root or repo_root()) / "data" / "raw").resolve()


def assert_in_data_raw(target: str | Path, *, allowed_root: Path | None = None) -> Path:
    """Resolve an output path and refuse anything outside `data/raw/`.

    `allowed_root` exists so tests can point at a temporary directory instead of writing client
    data paths during a test run. The CLI never passes it.
    """
    root = (allowed_root or data_raw_root()).resolve()
    path = Path(target).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if root not in path.parents:
        raise OutsideDataRaw(f"{path} is outside {root}; extract.py writes only to data/raw/")
    return path


class ReadOnlySession:
    """Wraps a DB-API connection and enforces read-only plus SELECT-only.

    The read-only statement is issued once, first, on construction. Every later statement goes
    through `select`, which refuses anything that is not a SELECT.
    """

    def __init__(self, connection) -> None:
        self._connection = connection
        read_only = getattr(connection, "read_only", None)
        if read_only is not None or hasattr(connection, "read_only"):
            try:
                connection.read_only = True
            except Exception:  # a driver that exposes it but refuses after connect
                pass
        with connection.cursor() as cursor:
            cursor.execute(READ_ONLY_STATEMENT)
        self._verified = True

    @property
    def connection(self):
        return self._connection

    def cursor(self, *args, **kwargs):
        return self._connection.cursor(*args, **kwargs)

    def select(self, cursor, statement, params=None):
        """Execute one SELECT. `statement` may be a psycopg Composed object."""
        assert_select_only(statement if isinstance(statement, str) else statement.as_string(self._connection))
        cursor.execute(statement, params)
        return cursor


def connect(connect_fn=None):
    """Open a read-only session. `connect_fn` is injected by tests."""
    if connect_fn is None:  # pragma: no cover - exercised only against a real database
        import psycopg

        def connect_fn(url):
            return psycopg.connect(url)

    return ReadOnlySession(connect_fn(database_url()))
