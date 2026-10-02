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
