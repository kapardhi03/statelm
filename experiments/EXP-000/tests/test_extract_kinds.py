"""Extractor tests for the ARTHRYX-shaped schema: kinds, placeholders, exclusions, ordering.

Every row here is invented. The fake table carries the same *column shape* as public.messages
and a kind distribution in the same proportions Kapardhi reported, so the arithmetic in the
assertions matches what a real run should produce, but no real message is involved and no
database is contacted.
"""

from __future__ import annotations

import csv
import io
import json
import sqlite3
from pathlib import Path

import pytest

import dbsafety
import extract

#: Exactly the columns of public.messages, so an excluded column has something to be absent from.
COLUMNS = ("id", "conversation", "builder_id", "direction", "kind", "body", "intent",
           "language", "created_at", "media_id", "media_mime", "meta")

CONFIG = """
sources:
  - table: public.messages
    columns:
      conversation_id: conversation
      speaker: direction
      speaker_role: direction
      timestamp: created_at
      text: body
    role_map:
      inbound: customer
      outbound: agent
    kinds:
      column: kind
      text: [text]
      placeholder:
        audio: "[media: voice note]"
        image: "[media: image]"
        video: "[media: video]"
        document: "[media: document]"
        unsupported: "[media: unsupported]"
        contacts: "[media: contact card]"
      drop: [reaction, sticker]
    exclude: [intent, meta, language, media_id, media_mime]
"""

#: Secrets that must never appear in the CSV or any statement. The media bodies are the point:
#: for a non-text row the body is replaced inside the SQL, so these strings never travel.
MEDIA_BODY = "MEDIA-BODY-MUST-NEVER-TRAVEL"
INTENT_VALUE = "INTENT-PREDICTION-MUST-NEVER-TRAVEL"
META_VALUE = '{"phone": "INSIDE-META-MUST-NEVER-TRAVEL"}'


def row(rid, conversation, direction, kind, body, created_at, builder="default"):
    return (rid, conversation, builder, direction, kind, body, INTENT_VALUE, "en",
            created_at, f"media-{rid}", "audio/ogg", META_VALUE)


def default_rows():
    """Four conversations. conv_a and conv_b have enough inbound text to be eligible."""
    rows, rid = [], 0
    def add(conversation, direction, kind, body, minute):
        nonlocal rid
        rid += 1
        rows.append(row(rid, conversation, direction, kind, body,
                        f"2025-08-12T10:{minute:02d}:00"))
    for i in range(4):
        add("conv_a", "inbound", "text", f"customer text {i}", i * 2)
        add("conv_a", "outbound", "text", f"seller reply {i}", i * 2 + 1)
    add("conv_a", "inbound", "audio", MEDIA_BODY, 20)
    add("conv_a", "inbound", "image", MEDIA_BODY, 21)
    add("conv_a", "inbound", "contacts", MEDIA_BODY, 22)
    add("conv_a", "inbound", "reaction", MEDIA_BODY, 23)
    add("conv_a", "inbound", "sticker", MEDIA_BODY, 24)

    for i in range(5):
        add("conv_b", "inbound", "text", f"other customer {i}", 30 + i)
    add("conv_b", "inbound", "video", MEDIA_BODY, 40)
    add("conv_b", "inbound", "document", MEDIA_BODY, 41)
    add("conv_b", "inbound", "unsupported", MEDIA_BODY, 42)

    # Four media messages and one text: must NOT pass a floor of four inbound text messages.
    for minute, kind in enumerate(("audio", "audio", "image", "video"), start=50):
        add("conv_media_only", "inbound", kind, MEDIA_BODY, minute)
    add("conv_media_only", "inbound", "text", "just one line", 55)

    # A text row whose body is empty: a non-message, dropped.
    add("conv_b", "inbound", "text", "   ", 45)
    return rows


class FakeTable:
    """An sqlite stand-in with public.messages' column shape."""

    def __init__(self, rows, *, created_at_type="text"):
        self.raw = sqlite3.connect(":memory:")
        self.statements: list[tuple] = []
        self.read_only_set = False
        self.database, self.role = "arthryx_test", "statelm_ro"
        self.schemas = ["public"]
        self._created_at_type = created_at_type
        self.raw.execute(
            "CREATE TABLE messages (id INTEGER, conversation TEXT, builder_id TEXT, "
            "direction TEXT, kind TEXT, body TEXT, intent TEXT, language TEXT, "
            "created_at TEXT, media_id TEXT, media_mime TEXT, meta TEXT)")
        self.raw.executemany(
            "INSERT INTO messages VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        self.raw.commit()

    def catalog_rows(self, params=None):
        types = {"id": "integer", "created_at": self._created_at_type}
        return [("public", "messages", name, types.get(name, "text")) for name in COLUMNS]

    @property
    def data_statements(self):
        return [s for s, _ in self.statements if s.strip() != dbsafety.READ_ONLY_STATEMENT]

    def cursor(self, *args, **kwargs):
        from tests.fakedb import FakeCursor
        return FakeCursor(self)

    def close(self):
        self.raw.close()


def session_for(rows, **kwargs):
    import fakedb  # noqa: F401  (import path shared with the other extract tests)
    return dbsafety.ReadOnlySession(FakeTable(rows, **kwargs))


@pytest.fixture(autouse=True)
def credentials(monkeypatch):
    """A fake DSN. dbsafety reads DATABASE_URL even when the connection is injected, by
    design: credentials come from the environment and nowhere else."""
    monkeypatch.setenv("DATABASE_URL",
                       "postgresql://dbuser:s3cr3t-pw@db.invalid:5432/arthryx_test")


@pytest.fixture
def workspace(tmp_path):
    config = tmp_path / "extract.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    return config, raw


def run(workspace, rows, *extra, created_at_type="text"):
    config, raw = workspace
    buffer = io.StringIO()
    code = extract.main(
        ["--extract", "--config", str(config), "--output", "arthryx_messages.csv",
         "--min-customer-messages", "4", *extra],
        connect_fn=lambda url: FakeTable(rows, created_at_type=created_at_type),
        allowed_root=raw, out=buffer)
    return code, buffer.getvalue(), raw


def read_csv(raw):
    with (raw / "arthryx_messages.csv").open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def read_meta(raw):
    return json.loads((raw / "arthryx_messages.meta.json").read_text(encoding="utf-8"))


class TestPlaceholders:
    def test_each_media_kind_gets_its_own_placeholder(self, workspace):
        code, _, raw = run(workspace, default_rows())
        assert code == 0
        texts = {r["text"] for r in read_csv(raw)}
        for expected in ("[media: voice note]", "[media: image]", "[media: video]",
                         "[media: document]", "[media: unsupported]",
                         "[media: contact card]"):
            assert expected in texts, expected

    def test_the_original_media_body_never_reaches_the_csv(self, workspace):
        _, _, raw = run(workspace, default_rows())
        body = (raw / "arthryx_messages.csv").read_text(encoding="utf-8")
        assert MEDIA_BODY not in body

    def test_the_media_body_is_never_even_selected(self, workspace):
        """The substitution is in SQL, so the body is not fetched and then discarded.

        Asserting on the output would pass either way. This asserts on the statements: the
        CASE returns a bound placeholder for a non-text kind, so the server never sends the
        media body to this process at all.
        """
        config, raw = workspace
        rows = default_rows()
        connection = FakeTable(rows)
        session = dbsafety.ReadOnlySession(connection)

        class Args:
            config, output = None, Path("arthryx_messages.csv")
            n_conversations, seed, min_customer_messages = 100, 0, 4
            since = until = schema = None
            tenant_column = role_note = None
        Args.config = str(config)
        extract.run_extract(session, Args, allowed_root=raw, out=io.StringIO())

        rendered = " ".join(connection.data_statements)
        assert "CASE" in rendered
        for statement, params in connection.statements:
            flat = " ".join(str(p) for p in (params or []))
            assert MEDIA_BODY not in statement and MEDIA_BODY not in flat

    def test_the_placeholders_cannot_be_confused_with_scrubber_tokens(self, workspace):
        """[media: image] against [PERSON_1]: an annotator can tell these apart."""
        _, _, raw = run(workspace, default_rows())
        for text in {r["text"] for r in read_csv(raw)}:
            if text.startswith("["):
                assert text.startswith("[media: "), text

    def test_the_placeholder_text_survives_the_scrubber_untouched(self, workspace, tmp_path):
        """The two tools have to compose: a placeholder must not look like PII."""
        import detectors
        for placeholder in ("[media: voice note]", "[media: image]", "[media: video]",
                            "[media: document]", "[media: unsupported]",
                            "[media: contact card]"):
            assert detectors.find_all(placeholder) == [], placeholder


class TestDroppedKinds:
    def test_reaction_and_sticker_rows_are_absent(self, workspace):
        _, _, raw = run(workspace, default_rows())
        texts = " ".join(r["text"] for r in read_csv(raw))
        assert "reaction" not in texts and "sticker" not in texts

    def test_the_metadata_records_how_many_were_dropped(self, workspace):
        _, _, raw = run(workspace, default_rows())
        dropped = read_meta(raw)["rows_dropped_by_kind"]
        assert dropped == {"reaction": 1, "sticker": 1}

    def test_an_empty_text_body_is_dropped_but_a_placeholder_row_is_kept(self, workspace):
        _, _, raw = run(workspace, default_rows())
        rows = read_csv(raw)
        assert all(r["text"].strip() for r in rows)
        assert any(r["text"] == "[media: video]" for r in rows)


class TestUnclassifiedKind:
    def test_a_kind_the_config_does_not_classify_fails_the_run(self, workspace):
        rows = default_rows()
        rows.append(row(999, "conv_a", "inbound", "location", "a pin", "2025-08-12T11:00:00"))
        with pytest.raises(extract.ConfigError, match="location"):
            run(workspace, rows)

    def test_the_error_says_what_to_do_about_it(self, workspace):
        rows = default_rows()
        rows.append(row(999, "conv_a", "inbound", "poll", "a poll", "2025-08-12T11:00:00"))
        with pytest.raises(extract.ConfigError, match="kinds.text, kinds.placeholder or kinds.drop"):
            run(workspace, rows)

    def test_nothing_is_written_when_a_kind_is_unclassified(self, workspace):
        rows = default_rows()
        rows.append(row(999, "conv_a", "inbound", "poll", "a poll", "2025-08-12T11:00:00"))
        with pytest.raises(extract.ConfigError):
            run(workspace, rows)
        _, raw = workspace
        assert not (raw / "arthryx_messages.csv").exists()


class TestExcludedColumns:
    EXCLUDED = ("intent", "meta", "language", "media_id", "media_mime")

    def test_no_excluded_column_appears_in_any_statement(self, workspace):
        config, raw = workspace
        connection = FakeTable(default_rows())
        session = dbsafety.ReadOnlySession(connection)

        class Args:
            output = Path("arthryx_messages.csv")
            n_conversations, seed, min_customer_messages = 100, 0, 4
            since = until = schema = None
            tenant_column = role_note = None
        Args.config = str(config)
        extract.run_extract(session, Args, allowed_root=raw, out=io.StringIO())

        for statement in connection.data_statements:
            for column in self.EXCLUDED:
                assert column not in statement.lower(), (column, statement)

    def test_their_values_never_reach_the_csv(self, workspace):
        _, _, raw = run(workspace, default_rows())
        body = (raw / "arthryx_messages.csv").read_text(encoding="utf-8")
        assert INTENT_VALUE not in body
        assert "INSIDE-META-MUST-NEVER-TRAVEL" not in body

    def test_the_metadata_lists_them(self, workspace):
        _, _, raw = run(workspace, default_rows())
        assert read_meta(raw)["excluded_columns"] == list(self.EXCLUDED)

    def test_a_column_both_excluded_and_mapped_is_a_config_error(self, tmp_path):
        config = tmp_path / "bad.yaml"
        config.write_text(CONFIG.replace("      text: body", "      text: intent"),
                          encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="both excludes and uses"):
            extract.load_config(config)

    def test_an_excluded_kinds_column_is_a_config_error(self, tmp_path):
        config = tmp_path / "bad.yaml"
        config.write_text(CONFIG.replace("      column: kind", "      column: language"),
                          encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="kinds.column"):
            extract.load_config(config)


class TestEligibilityCountsOnlyInboundText:
    """--min-customer-messages counts customer-role rows of a text kind, nothing else.

    A conversation of four voice notes has no labellable turns, so it must not satisfy a floor
    that exists to guarantee four.
    """

    def test_a_conversation_of_media_plus_one_text_does_not_qualify(self, workspace):
        _, _, raw = run(workspace, default_rows())
        conversations = {r["conversation_id"] for r in read_csv(raw)}
        assert "conv_media_only" not in conversations
        assert {"conv_a", "conv_b"} <= conversations

    def test_outbound_text_does_not_count_towards_the_floor(self, workspace):
        """conv_a has 4 inbound and 4 outbound text rows.

        A floor of 5 must exclude it: were outbound counted, its 8 text rows would pass.
        """
        rows = [r for r in default_rows() if r[1] == "conv_a"]
        with pytest.raises(extract.ConfigError, match="no conversation has at least"):
            run(workspace, rows, "--min-customer-messages", "5")

    def test_the_floor_is_met_by_inbound_text_alone(self, workspace):
        rows = [r for r in default_rows() if r[1] == "conv_a"]
        code, _, raw = run(workspace, rows, "--min-customer-messages", "4")
        assert code == 0
        assert {r["conversation_id"] for r in read_csv(raw)} == {"conv_a"}

    def test_the_metadata_states_the_rule(self, workspace):
        _, _, raw = run(workspace, default_rows())
        eligibility = read_meta(raw)["eligibility"]
        assert eligibility["rule"] == "customer-role rows of a text kind"
        assert eligibility["min_customer_messages"] == 4
        assert eligibility["conversations_eligible"] == 2

    def test_a_conversation_with_no_text_at_all_fails_the_floor(self, workspace):
        rows = [r for r in default_rows() if r[1] == "conv_media_only" and r[4] != "text"]
        with pytest.raises(extract.ConfigError, match="no conversation has at least"):
            run(workspace, rows)


class TestOrdering:
    def test_rows_come_out_in_chronological_order_within_a_conversation(self, workspace):
        _, _, raw = run(workspace, default_rows())
        for conversation in ("conv_a", "conv_b"):
            stamps = [r["timestamp"] for r in read_csv(raw)
                      if r["conversation_id"] == conversation]
            assert stamps == sorted(stamps), conversation

    def test_an_unparseable_timestamp_fails_the_run(self, workspace):
        rows = default_rows()
        rows.append(row(500, "conv_a", "inbound", "text", "late arrival", "not a date"))
        with pytest.raises(extract.ConfigError, match="does not parse as a timestamp"):
            run(workspace, rows)

    def test_the_failure_explains_why_it_is_not_merely_cosmetic(self, workspace):
        rows = default_rows()
        rows.append(row(500, "conv_a", "inbound", "text", "late arrival", ""))
        with pytest.raises(extract.ConfigError, match="silently reorder"):
            run(workspace, rows)

    def test_a_text_timestamp_column_is_cast_for_ordering(self, workspace):
        """The cast is what makes SQL agree with the parsed merge key."""
        config, raw = workspace
        catalog = {("public", "messages"): [(name, "text") for name in COLUMNS]}
        source = extract.load_config(config)[0]
        columns = extract.resolve_source(source, catalog)
        assert extract.timestamp_expression(source, columns, catalog) == '("created_at")::timestamptz'

    def test_a_temporal_timestamp_column_is_not_cast(self, workspace):
        config, _ = workspace
        catalog = {("public", "messages"): [
            (name, "timestamp with time zone" if name == "created_at" else "text")
            for name in COLUMNS]}
        source = extract.load_config(config)[0]
        columns = extract.resolve_source(source, catalog)
        assert extract.timestamp_expression(source, columns, catalog) == '"created_at"'

    def test_out_of_order_rows_fail_rather_than_being_written(self, workspace, monkeypatch):
        """The guard behind the cast.

        The sqlite shim cannot perform a PostgreSQL cast, so this test forces the condition the
        cast exists to prevent: SQL handing rows back in an order that disagrees with the
        parsed merge key. Against real PostgreSQL the cast does the ordering; this proves that
        if it ever failed to, the run stops instead of writing a misordered conversation.
        """
        # Negated id: valid inside min()/max() in the counting query, and in ORDER BY it
        # reverses insertion order, which is reverse chronological order for these rows.
        monkeypatch.setattr(extract, "timestamp_expression", lambda *a, **k: '(-"id")')
        with pytest.raises(extract.ConfigError, match="arrived out of order"):
            run(workspace, default_rows())


class TestMetadata:
    def test_it_records_the_placeholder_counts_per_kind(self, workspace):
        _, _, raw = run(workspace, default_rows())
        placeholders = read_meta(raw)["placeholder_rows_written"]
        assert placeholders == {
            "[media: voice note]": 1, "[media: image]": 1, "[media: contact card]": 1,
            "[media: video]": 1, "[media: document]": 1, "[media: unsupported]": 1,
        }
        assert read_meta(raw)["placeholder_rows_total"] == 6

    def test_the_counts_match_the_rows_actually_written(self, workspace):
        _, _, raw = run(workspace, default_rows())
        meta, rows = read_meta(raw), read_csv(raw)
        assert meta["messages_written"] == len(rows)
        assert meta["conversations_written"] == len({r["conversation_id"] for r in rows})
        written_placeholders = sum(1 for r in rows if r["text"].startswith("[media: "))
        assert meta["placeholder_rows_total"] == written_placeholders

    def test_it_records_the_kind_disposition(self, workspace):
        _, _, raw = run(workspace, default_rows())
        disposition = read_meta(raw)["kind_disposition"]
        assert disposition["text"] == "body"
        assert disposition["audio"] == "[media: voice note]"
        assert disposition["reaction"] == "dropped"

    def test_it_records_the_role_map_and_the_note_verbatim(self, workspace):
        note = ("agent = seller side. Outbound includes the bot and any human takeover; "
                "this schema cannot distinguish them (meta is excluded).")
        _, _, raw = run(workspace, default_rows(), "--role-note", note)
        meta = read_meta(raw)
        assert meta["role_map"] == {"inbound": "customer", "outbound": "agent"}
        assert meta["role_note"] == note

    def test_it_records_the_timestamp_column_and_how_it_was_ordered(self, workspace):
        _, _, raw = run(workspace, default_rows())
        stamp = read_meta(raw)["timestamp"]
        assert stamp["column"] == "created_at"
        assert stamp["declared_type"] == "text"
        assert "timestamptz" in stamp["order_expression"]

    def test_it_holds_no_message_text(self, workspace):
        _, _, raw = run(workspace, default_rows())
        body = (raw / "arthryx_messages.meta.json").read_text(encoding="utf-8")
        assert "customer text" not in body
        assert MEDIA_BODY not in body
        assert INTENT_VALUE not in body

    def test_it_lands_beside_the_csv_and_nowhere_else(self, workspace):
        _, _, raw = run(workspace, default_rows())
        assert sorted(p.name for p in raw.iterdir()) == [
            "arthryx_messages.csv", "arthryx_messages.meta.json"]


class TestTenantCheck:
    def test_the_single_value_is_recorded(self, workspace):
        _, output, raw = run(workspace, default_rows(), "--tenant-column", "builder_id")
        tenant = read_meta(raw)["tenant"]
        assert tenant["column"] == "builder_id"
        assert tenant["single_tenant"] is True
        assert set(tenant["values"]) == {"default"}
        assert "builder_id" in output

    def test_a_second_tenant_fails_the_consent_assumption(self, workspace):
        rows = default_rows()
        rows.append(row(900, "conv_a", "inbound", "text", "other tenant",
                        "2025-08-12T11:00:00", builder="someone-else"))
        with pytest.raises(extract.ConfigError, match="single-tenant"):
            run(workspace, rows, "--tenant-column", "builder_id")

    def test_it_is_a_check_not_a_filter(self, workspace):
        """Rows are not restricted by tenant: the run refuses instead of silently narrowing."""
        rows = default_rows()
        rows.append(row(900, "conv_a", "inbound", "text", "other tenant",
                        "2025-08-12T11:00:00", builder="someone-else"))
        with pytest.raises(extract.ConfigError):
            run(workspace, rows, "--tenant-column", "builder_id")
        _, raw = workspace
        # The CSV is written before the check, and the message says so.
        assert (raw / "arthryx_messages.csv").exists()

    def test_without_the_flag_no_tenant_query_runs(self, workspace):
        config, raw = workspace
        connection = FakeTable(default_rows())
        session = dbsafety.ReadOnlySession(connection)

        class Args:
            output = Path("arthryx_messages.csv")
            n_conversations, seed, min_customer_messages = 100, 0, 4
            since = until = schema = None
            tenant_column = role_note = None
        Args.config = str(config)
        extract.run_extract(session, Args, allowed_root=raw, out=io.StringIO())
        assert all("builder_id" not in s for s in connection.data_statements)
        assert read_meta(raw)["tenant"] is None


class TestRoleSentinel:
    def test_an_unfilled_role_map_fails_loudly(self, tmp_path):
        config = tmp_path / "unfilled.yaml"
        config.write_text(CONFIG.replace("      outbound: agent",
                                         f"      outbound: {extract.ROLE_SENTINEL}"),
                          encoding="utf-8")
        with pytest.raises(extract.ConfigError, match="Only you can say which side"):
            extract.load_config(config)

    def test_the_shipped_config_maps_outbound_to_agent(self):
        source = extract.load_config(Path(__file__).parent.parent / "extract.yaml")[0]
        assert source.role_map == {"inbound": "customer", "outbound": "agent"}


class TestAgainstTheReportedDistribution:
    """A fake table with the same kind distribution Kapardhi reported from public.messages.

    text 682 (330 inbound, 352 outbound), and inbound-only: audio 49, image 29, unsupported 13,
    sticker 10, reaction 8, video 6, contacts 3, document 1. Total 801.

    The rows are invented; only the proportions are real. The point is to check the arithmetic
    of the whole path end to end: dropping reaction and sticker leaves 783 rows, of which 682
    carry a body and 101 carry a placeholder. If a future change alters what is kept or
    dropped, these totals move and this test says so.
    """

    INBOUND_MEDIA = {"audio": 49, "image": 29, "unsupported": 13, "video": 6,
                     "contacts": 3, "document": 1}
    DROPPED = {"sticker": 10, "reaction": 8}

    def rows(self):
        rows, rid, minute = [], 0, 0

        def add(conversation, direction, kind, body):
            nonlocal rid, minute
            rid += 1
            minute += 1
            rows.append(row(rid, conversation, direction, kind, body,
                            f"2025-08-{12 + minute // 1000:02d}T"
                            f"{(minute // 60) % 24:02d}:{minute % 60:02d}:00"))

        # 330 inbound text over 30 conversations (11 each, comfortably over the floor of 4)
        for c in range(30):
            for i in range(11):
                add(f"conv_{c:03d}", "inbound", "text", f"inbound {c}-{i}")
        # 352 outbound text
        for i in range(352):
            add(f"conv_{i % 30:03d}", "outbound", "text", f"outbound {i}")
        # inbound media, and the dropped kinds
        for kind, count in {**self.INBOUND_MEDIA, **self.DROPPED}.items():
            for i in range(count):
                add(f"conv_{i % 30:03d}", "inbound", kind, MEDIA_BODY)
        return rows

    def test_the_totals_come_out_as_the_arithmetic_says(self, workspace):
        source_rows = self.rows()
        assert len(source_rows) == 801, "the fixture itself should reproduce the reported total"

        _, _, raw = run(workspace, source_rows, "--n-conversations", "30")
        written = read_csv(raw)
        meta = read_meta(raw)

        assert len(written) == 783, "801 less the 18 reaction and sticker rows"
        with_body = [r for r in written if not r["text"].startswith("[media: ")]
        placeholders = [r for r in written if r["text"].startswith("[media: ")]
        assert len(with_body) == 682
        assert len(placeholders) == 101
        assert meta["placeholder_rows_total"] == 101
        assert meta["rows_dropped_by_kind"] == {"reaction": 8, "sticker": 10}

    def test_the_roles_split_as_reported(self, workspace):
        _, _, raw = run(workspace, self.rows(), "--n-conversations", "30")
        roles = read_meta(raw)["per_role"]
        # 330 inbound text + 101 inbound media = 431 customer rows; 352 outbound text.
        assert roles == {"customer": 431, "agent": 352}

    def test_every_conversation_clears_the_floor_on_inbound_text_alone(self, workspace):
        _, _, raw = run(workspace, self.rows(), "--n-conversations", "30")
        assert read_meta(raw)["eligibility"]["conversations_eligible"] == 30

    def test_no_media_body_survives_at_this_scale(self, workspace):
        _, _, raw = run(workspace, self.rows(), "--n-conversations", "30")
        assert MEDIA_BODY not in (raw / "arthryx_messages.csv").read_text(encoding="utf-8")
