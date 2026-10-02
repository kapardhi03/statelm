"""Sampler tests on fabricated scrubbed conversations.

The assertions that matter most are the ones about what is *absent* from the sheets: no label,
no value, no cue, nothing that could prime an annotator.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

import pytest

import cues
import sample_items

FIELDS = """
fields:
  - name: budget
    type: amount
    description: Highest amount the customer will pay.
  - name: location_preference
    type: text
    description: Where the customer wants the property.
"""

TURNS = [
    ("SPEAKER_1", "customer", "looking for a 3BHK"),
    ("SPEAKER_2", "agent", "happy to help"),
    ("SPEAKER_1", "customer", "budget is around 40 lakhs"),
    ("SPEAKER_1", "customer", "actually make it 45"),
    ("SPEAKER_3", "bot", "automated note"),
    ("SPEAKER_1", "customer", "near Gachibowli please"),
    ("SPEAKER_2", "agent", "noted"),
    ("SPEAKER_1", "customer", "maybe 50 if it has parking"),
]


def write_conversations(root: Path, count: int = 3) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for c in range(1, count + 1):
        rows = [
            {"conversation_id": f"conv_{c:03d}", "turn_index": i, "timestamp": None,
             "timestamp_raw": "", "speaker_id": sp, "speaker_role": role, "text": text,
             "provenance": {"source": "human"}}
            for i, (sp, role, text) in enumerate(TURNS)
        ]
        (root / f"conv_{c:03d}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return root


@pytest.fixture
def workspace(tmp_path):
    source = write_conversations(tmp_path / "scrubbed")
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


def run(source, out, fields, *extra):
    buffer = io.StringIO()
    code = sample_items.main(
        ["--input", str(source), "--output", str(out), "--fields", str(fields), *extra],
        out=buffer)
    return code, buffer.getvalue()


def read_sheet(path):
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TestNoPreLabelling:
    def test_label_columns_are_empty(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        for row in read_sheet(out / "sheet_annotator_1.csv"):
            assert row["label"] == "" and row["value"] == "" and row["notes"] == ""

    def test_the_sheet_carries_no_stratum_or_cue(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        header = read_sheet(out / "sheet_annotator_1.csv")[0].keys()
        assert set(header) == set(sample_items.SHEET_COLUMNS)
        for forbidden in ("strata", "stratum", "cue", "hedge", "correction", "suggested"):
            assert forbidden not in {h.lower() for h in header}

    def test_no_cue_word_list_leaks_into_the_sheet_file(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        body = (out / "sheet_annotator_1.csv").read_text(encoding="utf-8")
        # "around" and "actually" appear in the conversation text, which is correct; the words
        # must not appear as a column, flag or annotation added by the tool.
        assert "hedge" not in body.lower() and "stratum" not in body.lower()

    def test_the_manifest_holds_the_strata_and_says_not_to_show_it(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert "do_not_show_to_annotators" in manifest
        assert manifest["turn_strata"]
        assert all(set(t["strata"]) <= set(cues.STRATA) for t in manifest["turn_strata"])


class TestSheets:
    def test_one_row_per_field_times_turn(self, workspace):
        source, fields, out = workspace
        _, output = run(source, out, fields, "--n-items", "12")
        rows = read_sheet(out / "sheet_annotator_1.csv")
        assert len(rows) == 12
        assert len({r["field"] for r in rows}) == 2
        assert len({(r["conversation_id"], r["turn_index"]) for r in rows}) == 6

    def test_trimming_happens_on_a_turn_boundary(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--n-items", "9")  # 9 // 2 fields = 4 turns -> 8 items
        rows = read_sheet(out / "sheet_annotator_1.csv")
        counts = {}
        for row in rows:
            counts.setdefault((row["conversation_id"], row["turn_index"]), 0)
            counts[(row["conversation_id"], row["turn_index"])] += 1
        assert set(counts.values()) == {2}  # no turn is half-labelled

    def test_context_is_shown_and_precedes_the_turn(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        rows = read_sheet(out / "sheet_annotator_1.csv")
        with_context = [r for r in rows if r["context"]]
        assert with_context
        row = with_context[0]
        assert "SPEAKER_" in row["context"]
        assert row["turn_text"] not in row["context"]

    def test_each_annotator_gets_an_identical_sheet(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        one = read_sheet(out / "sheet_annotator_1.csv")
        two = read_sheet(out / "sheet_annotator_2.csv")
        assert [r["item_id"] for r in one] == [r["item_id"] for r in two]
        assert one == two

    def test_item_ids_are_unique_and_joinable(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        ids = [r["item_id"] for r in read_sheet(out / "sheet_annotator_1.csv")]
        assert len(ids) == len(set(ids))
        assert all(id_.count("#") == 2 for id_ in ids)

    def test_annotator_names_are_configurable(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "kapardhi,second_rater")
        assert (out / "sheet_kapardhi.csv").exists()
        assert (out / "sheet_second_rater.csv").exists()

    def test_a_single_annotator_gets_the_fallback_warning(self, workspace):
        source, fields, out = workspace
        _, output = run(source, out, fields, "--annotators", "kapardhi")
        assert "intra-annotator" in output
        assert "blind to the first labels" in output


class TestSampling:
    def test_deterministic_for_a_seed(self, workspace):
        source, fields, out = workspace
        picks = []
        for _ in range(2):
            run(source, out, fields, "--n-items", "8", "--seed", "3")
            picks.append([r["item_id"] for r in read_sheet(out / "sheet_annotator_1.csv")])
        assert picks[0] == picks[1]

    def test_a_different_seed_can_select_differently(self, workspace):
        source, fields, out = workspace
        seen = set()
        for seed in range(6):
            run(source, out, fields, "--n-items", "4", "--seed", str(seed))
            seen.add(tuple(r["item_id"] for r in read_sheet(out / "sheet_annotator_1.csv")))
        assert len(seen) > 1

    def test_enrichment_reaches_the_cue_strata(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--n-items", "16")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        covered = {s for t in manifest["turn_strata"] for s in t["strata"]}
        assert {"correction", "hedge"} <= covered

    def test_shortfall_is_reported_not_hidden(self, tmp_path):
        source = tmp_path / "scrubbed"
        source.mkdir()
        (source / "conv_001.jsonl").write_text("".join(
            json.dumps({"conversation_id": "conv_001", "turn_index": i, "speaker_id": "SPEAKER_1",
                        "speaker_role": "customer", "text": "plain statement"}) + "\n"
            for i in range(6)), encoding="utf-8")
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        _, output = run(source, tmp_path / "annotation", fields, "--n-items", "8")
        assert "shortfall" in output
        manifest = json.loads((tmp_path / "annotation" / "manifest.json").read_text())
        assert manifest["enrichment"]["shortfall"]["hedge"] > 0

    def test_pilot_items_are_recorded_by_id_only(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--n-items", "8")
        payload = json.loads((out / "pilot_items.json").read_text(encoding="utf-8"))
        assert "must never enter the final test split" in payload["purpose"]
        assert payload["turns"] and all(
            set(t) == {"conversation_id", "turn_index"} for t in payload["turns"])
        body = (out / "pilot_items.json").read_text(encoding="utf-8")
        assert "Gachibowli" not in body and "40 lakhs" not in body


class TestInputsAndGuards:
    def test_a_missing_field_list_is_an_error(self, workspace, tmp_path):
        source, _, out = workspace
        empty = tmp_path / "empty.yaml"
        empty.write_text("fields: []\n", encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="non-empty"):
            run(source, out, empty)

    def test_a_field_without_a_name_is_an_error(self, workspace, tmp_path):
        source, _, out = workspace
        bad = tmp_path / "bad.yaml"
        bad.write_text("fields:\n  - type: amount\n", encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="needs at least a 'name'"):
            run(source, out, bad)

    def test_an_empty_input_directory_is_an_error(self, tmp_path):
        source = tmp_path / "scrubbed"
        source.mkdir()
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="no .jsonl conversations"):
            run(source, tmp_path / "annotation", fields)

    def test_output_nested_in_input_is_refused(self, workspace):
        import safety
        source, fields, _ = workspace
        with pytest.raises(safety.OutsideOutputRoot):
            run(source, source / "annotation", fields)

    def test_blank_turns_are_skipped(self, tmp_path):
        source = tmp_path / "scrubbed"
        source.mkdir()
        (source / "conv_001.jsonl").write_text("".join(
            json.dumps({"conversation_id": "conv_001", "turn_index": i,
                        "speaker_id": "SPEAKER_1", "speaker_role": "customer",
                        "text": "" if i % 2 else "real text"}) + "\n"
            for i in range(6)), encoding="utf-8")
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        run(source, tmp_path / "annotation", fields)
        rows = read_sheet(tmp_path / "annotation" / "sheet_annotator_1.csv")
        assert all(r["turn_text"].strip() for r in rows)


class TestLabelReference:
    def test_the_vocabulary_is_written_without_being_applied(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        body = (out / "labels_reference.txt").read_text(encoding="utf-8")
        for label in sample_items.LABEL_VOCABULARY:
            assert label in body
        assert "not the annotation guideline" in body

    def test_no_label_leaks_into_the_sheet(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        body = (out / "sheet_annotator_1.csv").read_text(encoding="utf-8")
        for label in sample_items.LABEL_VOCABULARY:
            assert label not in body


class TestLocalToolGuarantees:
    """The same two guarantees scrub.py carries, because this tool also reads client text."""

    def test_makes_no_network_call(self, workspace, monkeypatch):
        source, fields, out = workspace

        def boom(*args, **kwargs):
            raise AssertionError("sample_items.py must not open a network connection")

        import socket
        monkeypatch.setattr(socket, "socket", boom)
        monkeypatch.setattr(socket, "create_connection", boom)
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        code, _ = run(source, out, fields)
        assert code == 0

    def test_never_modifies_the_input(self, workspace):
        source, fields, out = workspace

        def fingerprint():
            return {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(source.rglob("*"))
                if path.is_file()
            }

        before = fingerprint()
        run(source, out, fields)
        assert fingerprint() == before
        assert before
