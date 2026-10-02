"""Reader and column-mapping tests, on fabricated exports."""

from __future__ import annotations

import pytest

import fixtures
import parsers


class TestColumnMap:
    def test_loads_required_and_optional_fields(self, tmp_path):
        path = fixtures.write_columns(tmp_path / "columns.yaml")
        mapping = parsers.load_column_map(path)
        assert mapping["conversation_id"] == "conv_id"
        assert mapping["role"] == "speaker_role"

    def test_role_may_be_absent(self, tmp_path):
        path = fixtures.write_columns(tmp_path / "c.yaml", fixtures.COLUMNS_YAML_NO_ROLE)
        assert "role" not in parsers.load_column_map(path)

    def test_a_missing_required_field_is_an_error(self, tmp_path):
        path = fixtures.write_columns(tmp_path / "c.yaml", "speaker: from\ntext: body\n")
        with pytest.raises(parsers.ColumnMapError, match="missing required field"):
            parsers.load_column_map(path)

    def test_an_unknown_field_is_an_error(self, tmp_path):
        body = fixtures.COLUMNS_YAML + "sentiment: mood\n"
        path = fixtures.write_columns(tmp_path / "c.yaml", body)
        with pytest.raises(parsers.ColumnMapError, match="unknown field"):
            parsers.load_column_map(path)

    def test_nothing_is_guessed_when_a_column_is_absent(self, tmp_path):
        # Reading the wrong column would corrupt the data with no visible symptom.
        path = fixtures.write_columns(tmp_path / "c.yaml")
        mapping = parsers.load_column_map(path)
        csv_path = fixtures.write_csv(tmp_path / "in" / "a.csv",
                                      [{"conv_id": "1", "from": "x", "sent_at": "", "body": "y"}])
        with pytest.raises(parsers.ColumnMapError, match="is not present"):
            parsers.read_csv(csv_path, mapping)


class TestReaders:
    @pytest.fixture
    def mapping(self, tmp_path):
        return parsers.load_column_map(fixtures.write_columns(tmp_path / "columns.yaml"))

    def test_csv(self, tmp_path, mapping):
        messages = parsers.read_csv(fixtures.write_csv(tmp_path / "in" / "a.csv"), mapping)
        assert len(messages) == len(fixtures.ROWS)
        assert messages[0].speaker == "Priya Sharma"
        assert messages[0].role == "customer"

    def test_json_list(self, tmp_path, mapping):
        messages = parsers.read_json(fixtures.write_json(tmp_path / "in" / "a.json"), mapping)
        assert len(messages) == len(fixtures.ROWS)

    def test_json_wrapped_in_one_list_key(self, tmp_path, mapping):
        import json
        path = tmp_path / "in" / "w.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"messages": fixtures.ROWS}), encoding="utf-8")
        assert len(parsers.read_json(path, mapping)) == len(fixtures.ROWS)

    def test_json_with_two_list_keys_is_an_error(self, tmp_path, mapping):
        import json
        path = tmp_path / "in" / "w.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"a": [], "b": fixtures.ROWS}), encoding="utf-8")
        with pytest.raises(parsers.ColumnMapError, match="exactly one"):
            parsers.read_json(path, mapping)

    def test_xlsx(self, tmp_path, mapping):
        messages = parsers.read_xlsx(fixtures.write_xlsx(tmp_path / "in" / "a.xlsx"), mapping)
        assert len(messages) == len(fixtures.ROWS)
        assert messages[0].speaker == "Priya Sharma"


class TestDiscover:
    def test_finds_all_three_formats_and_ignores_others(self, tmp_path):
        root = tmp_path / "in"
        fixtures.write_csv(root / "a.csv")
        fixtures.write_json(root / "b.json")
        fixtures.write_xlsx(root / "c.xlsx")
        (root / "notes.txt").write_text("ignored", encoding="utf-8")
        (root / "~$c.xlsx").write_text("lock file", encoding="utf-8")
        assert [p.name for p in parsers.discover(root)] == ["a.csv", "b.json", "c.xlsx"]

    def test_a_missing_directory_is_an_error(self, tmp_path):
        with pytest.raises(parsers.ColumnMapError, match="not a directory"):
            parsers.discover(tmp_path / "nope")


class TestSidecarsAreNotInputs:
    """extract.py writes `<output>.meta.json` into the same tree the scrubber scans.

    Without an exclusion the scrubber reads the run's own counts as a conversation export and
    fails with a column-mapping error, which is how this was found: the cross-tool test in
    test_extract.py broke the moment extract.py started writing the sidecar.
    """

    def test_a_meta_json_sidecar_is_skipped(self, tmp_path):
        (tmp_path / "arthryx_messages.csv").write_text(
            "conversation_id,speaker,speaker_role,timestamp,text\n"
            "c1,inbound,customer,2025-08-12T10:00:00,hello\n", encoding="utf-8")
        (tmp_path / "arthryx_messages.meta.json").write_text(
            '{"messages_written": 1, "per_role": {"customer": 1}}', encoding="utf-8")
        found = [p.name for p in parsers.discover(tmp_path)]
        assert found == ["arthryx_messages.csv"]

    def test_an_ordinary_json_export_is_still_found(self, tmp_path):
        (tmp_path / "export.json").write_text('[]', encoding="utf-8")
        assert [p.name for p in parsers.discover(tmp_path)] == ["export.json"]

    def test_the_exclusion_is_by_full_name_not_suffix(self, tmp_path):
        """A file merely containing "meta" is an export; only the sidecar suffix is excluded."""
        (tmp_path / "metadata_export.json").write_text('[]', encoding="utf-8")
        assert [p.name for p in parsers.discover(tmp_path)] == ["metadata_export.json"]
