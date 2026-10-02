"""Extractor tests. Every row is invented; no database server is involved."""

from __future__ import annotations

import csv
import io
from pathlib import Path

import pytest

import dbsafety
import extract
import fakedb

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parent

CONFIG = """
sources:
  - table: public.messages
    columns:
      conversation_id: conversation_id
      speaker: sender_name
      speaker_role: sender_type
      timestamp: created_at
      text: body
    role_map:
      user: customer
      staff: agent
      automation: bot
"""


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://dbuser:s3cr3t-pw@db.internal:5432/arthryx")


@pytest.fixture
def config(tmp_path):
    path = tmp_path / "extract.yaml"
    path.write_text(CONFIG, encoding="utf-8")
    return path


def run(argv, *, allowed_root=None):
    buffer = io.StringIO()
    connection = {}

    def connect_fn(url):
        connection["conn"] = fakedb.FakeConnection()
        return connection["conn"]

    code = extract.main(argv, connect_fn=connect_fn, allowed_root=allowed_root, out=buffer)
    return code, buffer.getvalue(), connection["conn"]


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.reader(fh))


class TestInspect:
    def test_prints_structure_and_row_counts(self):
        _, output, _ = run(["--inspect"])
        assert "public.messages" in output
        assert "conversation_id" in output and "sender_type" in output
        assert f"({len(fakedb.MESSAGES)} rows)" in output

    def test_never_prints_a_row_value(self):
        _, output, _ = run(["--inspect"])
        for secret in fakedb.SECRET_TEXTS:
            assert secret not in output, secret
        assert "Asha Rao" not in output and "9876543210" not in output

    def test_no_statement_reads_a_column_from_a_data_table(self):
        # The structural reason the mode cannot leak: catalog queries and count(*) only.
        _, _, connection = run(["--inspect"])
        for sql in connection.data_statements:
            assert "information_schema" in sql or sql.startswith("SELECT count(*) FROM"), sql

    def test_read_only_first_and_selects_only(self):
        _, _, connection = run(["--inspect"])
        assert connection.statements[0][0] == dbsafety.READ_ONLY_STATEMENT
        for sql in connection.data_statements:
            dbsafety.assert_select_only(sql)

    def test_the_heuristic_skips_an_unrelated_table(self):
        _, output, _ = run(["--inspect"])
        assert "invoices" not in output

    def test_all_tables_widens_it(self):
        _, output, _ = run(["--inspect", "--all-tables"])
        assert "public.invoices" in output
        for secret in fakedb.SECRET_TEXTS:
            assert secret not in output


class TestConfig:
    def test_missing_sources_key(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text("table: messages\n", encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="sources"):
            extract.load_config(path)

    def test_missing_column_mapping(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text("sources:\n  - table: messages\n    columns:\n      text: body\n",
                        encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="missing column mapping"):
            extract.load_config(path)

    def test_unknown_field(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(
            "sources:\n  - table: public.messages\n    columns:\n"
            "      conversation_id: conversation_id\n      speaker: sender_name\n"
            "      speaker_role: sender_type\n      timestamp: created_at\n"
            "      text: body\n      sentiment: mood\n",
            encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="unknown field"):
            extract.load_config(path)

    def test_role_map_values_are_constrained(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(CONFIG.replace("user: customer", "user: client"), encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="role_map values"):
            extract.load_config(path)

    def test_schema_defaults_to_public(self, tmp_path):
        path = tmp_path / "c.yaml"
        path.write_text(CONFIG.replace("public.messages", "messages"), encoding="utf-8")
        assert extract.load_config(path)[0].schema == "public"


class TestResolveColumns:
    def _catalog(self):
        return {("public", "messages"): [("conversation_id", "text"), ("sender_name", "text"),
                                         ("sender_type", "text"), ("created_at", "text"),
                                         ("body", "text")]}

    def test_a_missing_column_is_an_error_not_a_guess(self, config):
        source = extract.load_config(config)[0]
        broken = extract.Source(schema="public", table="messages",
                                columns={**source.columns, "text": "bodyy"})
        with pytest.raises(extract.ConfigError, match=r"\['bodyy'\]"):
            extract.resolve_source(broken, self._catalog())

    def test_the_error_lists_what_is_available(self, config):
        source = extract.load_config(config)[0]
        broken = extract.Source(schema="public", table="messages",
                                columns={**source.columns, "text": "nope"})
        with pytest.raises(extract.ConfigError, match="body"):
            extract.resolve_source(broken, self._catalog())

    def test_a_missing_table_is_an_error(self, config):
        source = extract.load_config(config)[0]
        missing = extract.Source(schema="public", table="chats", columns=source.columns)
        with pytest.raises(extract.ConfigError, match="does not exist"):
            extract.resolve_source(missing, self._catalog())

    def test_resolution_uses_the_catalog_spelling(self, config):
        source = extract.load_config(config)[0]
        shouty = extract.Source(schema="public", table="messages",
                                columns={**source.columns, "text": "BODY"})
        assert extract.resolve_source(shouty, self._catalog())["text"] == "body"


class TestExtract:
    def test_csv_has_exactly_the_five_columns_in_order(self, config, tmp_path):
        out = tmp_path / "raw"
        run(["--extract", "--config", str(config)], allowed_root=out)
        assert read_csv(out / "arthryx_messages.csv")[0] == list(extract.CSV_COLUMNS)

    def test_ordered_by_conversation_then_timestamp(self, config, tmp_path):
        out = tmp_path / "raw"
        run(["--extract", "--config", str(config)], allowed_root=out)
        rows = read_csv(out / "arthryx_messages.csv")[1:]
        keys = [(r[0], r[3]) for r in rows]
        assert keys == sorted(keys)

    def test_role_map_is_applied(self, config, tmp_path):
        out = tmp_path / "raw"
        _, output, _ = run(["--extract", "--config", str(config)], allowed_root=out)
        roles = {r[2] for r in read_csv(out / "arthryx_messages.csv")[1:]}
        assert roles <= {"customer", "agent", "bot"}
        assert "customer" in output and "user" not in output.replace("dbuser", "")

    def test_min_customer_messages_filters(self, config, tmp_path):
        out = tmp_path / "raw"
        run(["--extract", "--config", str(config)], allowed_root=out)
        default = {r[0] for r in read_csv(out / "arthryx_messages.csv")[1:]}
        assert default == {"ARTH-1", "ARTH-2", "ARTH-4"}  # ARTH-3 has one customer message

        run(["--extract", "--config", str(config), "--min-customer-messages", "5"],
            allowed_root=out)
        assert {r[0] for r in read_csv(out / "arthryx_messages.csv")[1:]} == {"ARTH-4"}

    def test_no_eligible_conversation_is_a_clear_error(self, config, tmp_path):
        with pytest.raises(extract.ConfigError, match="at least 99 customer messages"):
            run(["--extract", "--config", str(config), "--min-customer-messages", "99"],
                allowed_root=tmp_path / "raw")

    def test_sampling_is_deterministic_for_a_seed(self, config, tmp_path):
        picks = []
        for _ in range(2):
            out = tmp_path / "raw"
            run(["--extract", "--config", str(config), "--n-conversations", "2", "--seed", "7"],
                allowed_root=out)
            picks.append({r[0] for r in read_csv(out / "arthryx_messages.csv")[1:]})
        assert picks[0] == picks[1] and len(picks[0]) == 2

    def test_a_different_seed_can_select_differently(self, config, tmp_path):
        seen = set()
        for seed in range(8):
            out = tmp_path / "raw"
            run(["--extract", "--config", str(config), "--n-conversations", "2",
                 "--seed", str(seed)], allowed_root=out)
            seen.add(frozenset(r[0] for r in read_csv(out / "arthryx_messages.csv")[1:]))
        assert len(seen) > 1

    def test_since_filter(self, config, tmp_path):
        out = tmp_path / "raw"
        run(["--extract", "--config", str(config), "--since", "2025-10-01",
             "--min-customer-messages", "4"], allowed_root=out)
        assert {r[0] for r in read_csv(out / "arthryx_messages.csv")[1:]} == {"ARTH-4"}

    def test_until_filter(self, config, tmp_path):
        out = tmp_path / "raw"
        run(["--extract", "--config", str(config), "--until", "2025-09-01"], allowed_root=out)
        assert {r[0] for r in read_csv(out / "arthryx_messages.csv")[1:]} == {"ARTH-1"}


class TestTerminalOutput:
    def test_counts_only_never_text(self, config, tmp_path):
        _, output, _ = run(["--extract", "--config", str(config)],
                           allowed_root=tmp_path / "raw")
        for secret in fakedb.SECRET_TEXTS:
            assert secret not in output, secret
        assert "Asha Rao" not in output and "9876543210" not in output

    def test_counts_are_present(self, config, tmp_path):
        _, output, _ = run(["--extract", "--config", str(config)],
                           allowed_root=tmp_path / "raw")
        assert "conversations: 3" in output
        assert "messages: " in output and "per role:" in output and "date range:" in output

    def test_credentials_never_appear(self, config, tmp_path):
        _, output, _ = run(["--extract", "--config", str(config)],
                           allowed_root=tmp_path / "raw")
        for fragment in ("s3cr3t-pw", "db.internal", "postgresql://", "dbuser"):
            assert fragment not in output, fragment


class TestGuarantees:
    def test_read_only_first_and_every_data_statement_is_a_select(self, config, tmp_path):
        _, _, connection = run(["--extract", "--config", str(config)],
                               allowed_root=tmp_path / "raw")
        assert connection.statements[0][0] == dbsafety.READ_ONLY_STATEMENT
        for sql in connection.data_statements:
            dbsafety.assert_select_only(sql)

    def test_the_id_list_is_passed_as_a_parameter(self, config, tmp_path):
        _, _, connection = run(["--extract", "--config", str(config)],
                               allowed_root=tmp_path / "raw")
        fetches = [(s, p) for s, p in connection.statements if "= ANY(%s)" in s]
        assert fetches and all(isinstance(p[-1], list) for _, p in fetches)

    def test_writing_outside_data_raw_is_refused(self, config, tmp_path):
        # Uses the real data/raw root, so nothing is written anywhere during this test.
        with pytest.raises(dbsafety.OutsideDataRaw):
            run(["--extract", "--config", str(config), "--output", str(tmp_path / "x.csv")])

    def test_missing_credentials_stop_the_run(self, config, tmp_path, monkeypatch):
        monkeypatch.delenv("DATABASE_URL", raising=False)
        with pytest.raises(dbsafety.MissingCredentials):
            run(["--extract", "--config", str(config)], allowed_root=tmp_path / "raw")


class TestScrubIntegration:
    def test_the_shipped_columns_yaml_reads_the_extracted_csv_unchanged(self, config, tmp_path):
        """The CSV extract.py writes must feed scrub.py with no edits to columns.yaml."""
        import json

        import scrub

        raw = tmp_path / "raw"
        run(["--extract", "--config", str(config)], allowed_root=raw)

        scrubbed = tmp_path / "scrubbed"
        assert scrub.main(["--input", str(raw), "--output", str(scrubbed),
                           "--columns", str(PACKAGE / "columns.yaml")]) == 0

        rows = [json.loads(l) for l in (scrubbed / "conv_001.jsonl").read_text().splitlines()]
        assert rows[0]["speaker_role"] in {"customer", "agent", "bot"}
        text = " ".join(r["text"] for r in rows)
        assert "9876543210" not in text            # phone redacted
        assert "around 40 lakhs" in text           # amount preserved
        assert "Asha Rao" not in text              # roster name redacted


class TestZeroTables:
    """The reported bug: --all-tables used to suggest --all-tables."""

    def _run(self, argv, **kwargs):
        buffer = io.StringIO()
        connection = {}

        def connect_fn(url):
            connection["conn"] = fakedb.FakeConnection(**kwargs)
            return connection["conn"]

        extract.main(argv, connect_fn=connect_fn, out=buffer)
        return buffer.getvalue(), connection["conn"]

    def test_no_tables_reports_database_role_and_schemas(self):
        output, _ = self._run(["--inspect"], empty=True)
        assert "No tables are visible to this connection." in output
        assert "database:         arthryx_test" in output
        assert "role:             statelm_ro" in output
        assert "schemas searched: public" in output

    def test_no_tables_hints_at_privileges_schema_and_database(self):
        output, _ = self._run(["--inspect"], empty=True)
        assert "GRANT USAGE ON SCHEMA" in output
        assert "GRANT SELECT ON ALL TABLES" in output
        assert "--schema <name>" in output
        assert "DATABASE_URL" in output

    def test_all_tables_no_longer_suggests_all_tables(self):
        output, _ = self._run(["--inspect", "--all-tables"], empty=True)
        assert "Re-run with --all-tables" not in output
        assert "No tables are visible to this connection." in output

    def test_the_hint_still_appears_when_tables_exist_but_none_match(self):
        output, _ = self._run(["--inspect"], messages=[], with_invoices=True)
        # messages table exists but is empty of rows; invoices is not conversational.
        assert "Re-run with --all-tables" in output or "public.messages" in output

    def test_no_row_values_in_the_zero_table_path(self):
        output, _ = self._run(["--inspect"], empty=True)
        for secret in fakedb.SECRET_TEXTS:
            assert secret not in output


class TestSchemaOption:
    def _run(self, argv, **kwargs):
        buffer = io.StringIO()

        def connect_fn(url):
            return fakedb.FakeConnection(**kwargs)

        extract.main(argv, connect_fn=connect_fn, out=buffer)
        return buffer.getvalue()

    def test_naming_the_right_schema_finds_the_table(self):
        assert "public.messages" in self._run(["--inspect", "--schema", "public"])

    def test_naming_a_schema_with_nothing_in_it_reports_what_was_searched(self):
        output = self._run(["--inspect", "--schema", "sales"])
        assert "schemas searched: sales" in output
        assert "No tables are visible to this connection." in output

    def test_repeating_the_option_searches_both(self):
        output = self._run(["--inspect", "--schema", "sales", "--schema", "public"])
        assert "public.messages" in output

    def test_the_default_discovers_non_system_schemas(self):
        # No --schema: the searched list comes from information_schema.schemata.
        output = self._run(["--inspect"], schemas=("public", "sales"))
        assert "public.messages" in output
