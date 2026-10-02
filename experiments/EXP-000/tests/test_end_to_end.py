"""Full runs on fabricated exports, including the three guarantees scrub.py makes."""

from __future__ import annotations

import hashlib
import json

import pytest

import fixtures
import scrub


def tree_hashes(root):
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*")) if p.is_file()
    }


@pytest.fixture
def workspace(tmp_path):
    source = tmp_path / "raw"
    fixtures.write_csv(source / "arthryx.csv")
    columns = fixtures.write_columns(tmp_path / "columns.yaml")
    return tmp_path, source, columns, tmp_path / "scrubbed"


def run(source, out, columns, *extra):
    return scrub.main(["--input", str(source), "--output", str(out),
                       "--columns", str(columns), *extra])


def rows_of(out, name):
    return [json.loads(l) for l in (out / name).read_text(encoding="utf-8").splitlines()]


class TestOutput:
    def test_one_jsonl_per_conversation_with_mapped_ids(self, workspace):
        _, source, columns, out = workspace
        assert run(source, out, columns) == 0
        # Source ids ARTH-1 / ARTH-2 are not used as filenames: they can be identifying.
        assert sorted(p.name for p in out.glob("*.jsonl")) == ["conv_001.jsonl", "conv_002.jsonl"]

    def test_schema_fields_and_provenance(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        row = rows_of(out, "conv_001.jsonl")[0]
        assert row["schema"] == scrub.SCHEMA
        assert row["conversation_id"] == "conv_001"
        assert row["turn_index"] == 0
        assert row["speaker_id"] == "SPEAKER_1"
        assert row["speaker_role"] == "customer"
        assert row["timestamp"] == "2025-08-12T19:42:13"
        assert row["provenance"]["source"] == "human"
        assert row["provenance"]["labeler"] is None
        assert len(row["provenance"]["source_sha256"]) == 64

    def test_no_derived_fields_that_could_prime_an_annotator(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        row = rows_of(out, "conv_001.jsonl")[0]
        assert set(row) == {"schema", "conversation_id", "turn_index", "timestamp",
                            "timestamp_raw", "speaker_id", "speaker_role", "text", "provenance"}

    def test_amounts_survive_and_account_details_do_not(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        text = " ".join(r["text"] for r in rows_of(out, "conv_001.jsonl"))
        assert "around 40 lakhs" in text
        assert "might stretch to 45" in text
        assert "123456789012" not in text and "HDFC0001234" not in text
        assert "4111111111111111" not in text and "560001" not in text
        assert "9876543210" not in text and "desk@example.com" not in text

    def test_names_are_replaced_consistently_within_a_conversation(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        rows = rows_of(out, "conv_001.jsonl")
        assert "Priya" not in " ".join(r["text"] for r in rows)
        assert "[PERSON_1]" in rows[0]["text"] and "[PERSON_1]" in rows[1]["text"]

    def test_placeholders_restart_in_the_next_conversation(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        # Per-conversation scope, so the two cannot be linked.
        assert "[PERSON_1]" in rows_of(out, "conv_002.jsonl")[0]["text"]

    def test_unparseable_timestamp_keeps_its_raw_value(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        bad = [r for r in rows_of(out, "conv_001.jsonl") if r["timestamp"] is None]
        assert bad and bad[0]["timestamp_raw"] == "not a date"


class TestReports:
    def test_audit_lists_every_replacement_with_its_original(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        rows = rows_of(out, "_audit/audit.sensitive.jsonl")
        assert rows[0]["record"] == "warning" and "UNREDACTED" in rows[0]["message"]
        replacements = [r for r in rows if r["record"] == "replacement"]
        originals = {r["original"] for r in replacements}
        assert "desk@example.com" in originals and "123456789012" in originals
        assert {"conversation_id", "turn_index", "source_file", "source_row", "category",
                "original", "token"} <= set(replacements[0])

    def test_audit_carries_the_id_maps(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        rows = rows_of(out, "_audit/audit.sensitive.jsonl")
        conv = {r["source_conversation_id"]: r["conversation_id"]
                for r in rows if r["record"] == "conversation_id_map"}
        assert conv == {"ARTH-1": "conv_001", "ARTH-2": "conv_002"}
        assert any(r["record"] == "speaker_map" for r in rows)

    def test_summary_holds_counts_and_no_client_text(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        blob = json.dumps(summary)
        for secret in ("Priya", "desk@example.com", "123456789012", "40 lakhs", "MG Road"):
            assert secret not in blob, secret
        assert summary["contains_client_text"] is False
        assert summary["conversation_count"] == 2
        assert summary["replacements_by_category"]["EMAIL"] == 1

    def test_unmapped_speakers_are_listed(self, tmp_path):
        source = tmp_path / "raw"
        fixtures.write_csv(source / "a.csv")
        columns = fixtures.write_columns(tmp_path / "c.yaml", fixtures.COLUMNS_YAML_NO_ROLE)
        out = tmp_path / "out"
        run(source, out, columns)
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        assert summary["unmapped_speakers_count"] == 3

    def test_roles_csv_fills_in_when_the_export_has_no_role_column(self, tmp_path):
        source = tmp_path / "raw"
        fixtures.write_csv(source / "a.csv")
        columns = fixtures.write_columns(tmp_path / "c.yaml", fixtures.COLUMNS_YAML_NO_ROLE)
        roles = tmp_path / "roles.csv"
        roles.write_text("speaker,role\nPriya Sharma,customer\nArthryx Desk,agent\n",
                         encoding="utf-8")
        out = tmp_path / "out"
        run(source, out, columns, "--roles", str(roles))
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        assert summary["unmapped_speakers"] == ["Unknown Bot"]


class TestGuarantees:
    def test_input_is_never_modified(self, workspace):
        _, source, columns, out = workspace
        before = tree_hashes(source)
        run(source, out, columns)
        assert tree_hashes(source) == before

    def test_nothing_is_written_outside_the_output_folder(self, tmp_path, monkeypatch):
        source = tmp_path / "raw"
        fixtures.write_csv(source / "a.csv")
        columns = fixtures.write_columns(tmp_path / "columns.yaml")
        out = tmp_path / "out"
        elsewhere = tmp_path / "cwd"
        elsewhere.mkdir()
        monkeypatch.chdir(elsewhere)
        run(source, out, columns)
        assert list(elsewhere.iterdir()) == []
        written = {p for p in tmp_path.rglob("*") if p.is_file()}
        assert all(out in p.parents or p.parent in {source, tmp_path} for p in written)

    def test_no_network_calls(self, workspace, monkeypatch):
        _, source, columns, out = workspace

        def boom(*args, **kwargs):
            raise AssertionError("scrub.py must not open a network connection")

        import socket
        monkeypatch.setattr(socket, "socket", boom)
        monkeypatch.setattr(socket, "create_connection", boom)
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        assert run(source, out, columns) == 0

    def test_dry_run_writes_nothing(self, workspace, capsys):
        _, source, columns, out = workspace
        assert run(source, out, columns, "--dry-run") == 0
        assert not out.exists()
        assert "would write" in capsys.readouterr().out

    def test_output_nested_in_input_is_refused(self, workspace):
        import safety
        _, source, columns, _ = workspace
        with pytest.raises(safety.OutsideOutputRoot):
            run(source, source / "out", columns)


class TestModes:
    def test_check_mode_reports_a_clean_residual_scan(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns, "--check")
        summary = json.loads((out / "summary.json").read_text(encoding="utf-8"))
        assert summary["residual_scan"]["residual_hits_by_category"] == {}
        assert summary["residual_scan"]["checked_messages"] == 6

    def test_scrubbing_is_idempotent(self, tmp_path):
        """Re-scrubbing scrubbed text must not nest placeholders."""
        source = tmp_path / "raw"
        fixtures.write_csv(source / "a.csv", [
            {"conv_id": "X", "from": "A", "sent_at": "2025-01-01 00:00:00",
             "body": "ping [PHONE_1] and [EMAIL_1]", "speaker_role": "agent"}])
        columns = fixtures.write_columns(tmp_path / "c.yaml")
        out = tmp_path / "out"
        run(source, out, columns)
        assert rows_of(out, "conv_001.jsonl")[0]["text"] == "ping [PHONE_1] and [EMAIL_1]"

    def test_localities_survive_by_default_and_premise_numbers_do_not(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns)
        text = " ".join(r["text"] for r in rows_of(out, "conv_001.jsonl"))
        assert "MG Road" in text          # a road is state, not an identifier
        assert "Flat [ADDRESS_" in text   # the flat number went
        assert "560001" not in text       # pincode went

    def test_address_clauses_are_opt_in(self, workspace):
        _, source, columns, out = workspace
        run(source, out, columns, "--address-clauses")
        text = " ".join(r["text"] for r in rows_of(out, "conv_001.jsonl"))
        assert "MG Road" not in text      # the blunt rule, only when asked for

    def test_a_property_preference_is_not_touched(self, tmp_path):
        source = tmp_path / "raw"
        fixtures.write_csv(source / "a.csv", [
            {"conv_id": "P", "from": "Asha", "sent_at": "2025-01-01 00:00:00",
             "body": "3BHK flat near Gachibowli, budget 80 lakhs", "speaker_role": "customer"}])
        columns = fixtures.write_columns(tmp_path / "c.yaml")
        out = tmp_path / "out"
        run(source, out, columns)
        assert rows_of(out, "conv_001.jsonl")[0]["text"] == (
            "3BHK flat near Gachibowli, budget 80 lakhs")

    def test_all_three_formats_produce_the_same_scrubbed_text(self, tmp_path):
        columns = fixtures.write_columns(tmp_path / "c.yaml")
        texts = {}
        for name, writer in (("csv", fixtures.write_csv), ("json", fixtures.write_json),
                             ("xlsx", fixtures.write_xlsx)):
            source, out = tmp_path / f"in_{name}", tmp_path / f"out_{name}"
            writer(source / f"a.{name}")
            run(source, out, columns)
            texts[name] = [r["text"] for r in rows_of(out, "conv_001.jsonl")]
        assert texts["csv"] == texts["json"] == texts["xlsx"]
