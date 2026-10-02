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
        for row in read_sheet(out / "sheet_A.csv"):
            assert row["label"] == "" and row["value"] == "" and row["notes"] == ""

    def test_the_sheet_carries_no_stratum_or_cue(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        header = read_sheet(out / "sheet_A.csv")[0].keys()
        assert set(header) == set(sample_items.SHEET_COLUMNS)
        for forbidden in ("strata", "stratum", "cue", "hedge", "correction", "suggested"):
            assert forbidden not in {h.lower() for h in header}

    def test_no_cue_word_list_leaks_into_the_sheet_file(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        body = (out / "sheet_A.csv").read_text(encoding="utf-8")
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
        rows = read_sheet(out / "sheet_A.csv")
        assert len(rows) == 12
        assert len({r["field"] for r in rows}) == 2
        assert len({(r["conversation_id"], r["turn_index"]) for r in rows}) == 6

    def test_trimming_happens_on_a_turn_boundary(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--n-items", "9")  # 9 // 2 fields = 4 turns -> 8 items
        rows = read_sheet(out / "sheet_A.csv")
        counts = {}
        for row in rows:
            counts.setdefault((row["conversation_id"], row["turn_index"]), 0)
            counts[(row["conversation_id"], row["turn_index"])] += 1
        assert set(counts.values()) == {2}  # no turn is half-labelled

    def test_context_is_shown_and_precedes_the_turn(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        rows = read_sheet(out / "sheet_A.csv")
        with_context = [r for r in rows if r["context"]]
        assert with_context
        row = with_context[0]
        assert "SPEAKER_" in row["context"]
        assert row["turn_text"] not in row["context"]

    def test_each_annotator_gets_the_same_items(self, workspace):
        """Same items, same content per item. The *order* differs by design: see
        TestInterAnnotatorSheetOrder."""
        source, fields, out = workspace
        run(source, out, fields)
        one = read_sheet(out / "sheet_A.csv")
        two = read_sheet(out / "sheet_B.csv")
        assert {r["item_id"] for r in one} == {r["item_id"] for r in two}
        by_id = lambda rows: sorted(rows, key=lambda r: r["item_id"])
        assert by_id(one) == by_id(two)

    def test_item_ids_are_unique_and_joinable(self, workspace):
        source, fields, out = workspace
        run(source, out, fields)
        ids = [r["item_id"] for r in read_sheet(out / "sheet_A.csv")]
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
            picks.append([r["item_id"] for r in read_sheet(out / "sheet_A.csv")])
        assert picks[0] == picks[1]

    def test_a_different_seed_can_select_differently(self, workspace):
        source, fields, out = workspace
        seen = set()
        for seed in range(6):
            run(source, out, fields, "--n-items", "4", "--seed", str(seed))
            seen.add(tuple(r["item_id"] for r in read_sheet(out / "sheet_A.csv")))
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
        rows = read_sheet(tmp_path / "annotation" / "sheet_A.csv")
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
        body = (out / "sheet_A.csv").read_text(encoding="utf-8")
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


class TestInterAnnotatorSheetOrder:
    """Each annotator gets the same items in their own seeded order."""

    def test_the_default_annotators_are_letters_not_names(self):
        assert sample_items.DEFAULT_ANNOTATORS == ("A", "B")

    def test_annotators_can_be_space_separated(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        assert (out / "sheet_A.csv").exists() and (out / "sheet_B.csv").exists()

    def test_annotators_can_still_be_comma_separated(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A,B")
        assert (out / "sheet_A.csv").exists() and (out / "sheet_B.csv").exists()

    def test_a_repeated_annotator_is_an_error(self, workspace):
        source, fields, out = workspace
        with pytest.raises(sample_items.SamplerError, match="repeats a name"):
            run(source, out, fields, "--annotators", "A", "A")

    def test_both_sheets_hold_the_same_items(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        a = [row["item_id"] for row in read_sheet(out / "sheet_A.csv")]
        b = [row["item_id"] for row in read_sheet(out / "sheet_B.csv")]
        assert set(a) == set(b)
        assert len(a) == len(b) == len(set(a))

    def test_but_in_different_orders(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        a = [row["item_id"] for row in read_sheet(out / "sheet_A.csv")]
        b = [row["item_id"] for row in read_sheet(out / "sheet_B.csv")]
        assert a != b

    def test_the_order_is_recorded_in_the_manifest(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        order = manifest["sheet_order"]
        a = [row["item_id"] for row in read_sheet(out / "sheet_A.csv")]
        assert order["item_order"]["A"] == a
        assert order["orders_distinct"] is True
        assert set(order["seeds"]) == {"A", "B"}

    def test_the_same_seed_reproduces_both_orders(self, workspace, tmp_path):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B", "--seed", "3")
        first = [row["item_id"] for row in read_sheet(out / "sheet_A.csv")]
        second_out = tmp_path / "again"
        run(source, second_out, fields, "--annotators", "A", "B", "--seed", "3")
        assert [row["item_id"] for row in read_sheet(second_out / "sheet_A.csv")] == first

    def test_a_different_seed_gives_a_different_order(self, workspace, tmp_path):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B", "--seed", "3")
        first = [row["item_id"] for row in read_sheet(out / "sheet_A.csv")]
        other = tmp_path / "other"
        run(source, other, fields, "--annotators", "A", "B", "--seed", "4")
        assert [row["item_id"] for row in read_sheet(other / "sheet_A.csv")] != first

    def test_adding_an_annotator_does_not_disturb_the_others(self, workspace, tmp_path):
        """The per-annotator seed is derived from the name, not from draw order."""
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        a_before = [row["item_id"] for row in read_sheet(out / "sheet_A.csv")]
        three = tmp_path / "three"
        run(source, three, fields, "--annotators", "A", "B", "C")
        assert [row["item_id"] for row in read_sheet(three / "sheet_A.csv")] == a_before

    def test_one_item_cannot_be_permuted_and_says_so(self, tmp_path):
        """With a single item every order is the same order, so the run reports it."""
        source = write_conversations(tmp_path / "scrubbed", count=1)
        for path in source.glob("*.jsonl"):
            first = path.read_text(encoding="utf-8").splitlines()[0]
            path.write_text(first + "\n", encoding="utf-8")
        fields = tmp_path / "one.yaml"
        fields.write_text("fields:\n  - name: budget\n", encoding="utf-8")
        code, output = run(source, tmp_path / "out", fields, "--annotators", "A", "B",
                           "--n-items", "1")
        assert code == 0
        manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["sheet_order"]["orders_distinct"] is False
        assert "does not exist" in manifest["sheet_order"]["note"]
        assert "WARNING" in output

    def test_no_personal_name_appears_in_any_annotation_artifact(self, workspace):
        """A, B and nothing else. Which person is which letter is not recorded here."""
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        for path in sorted(out.iterdir()):
            if path.is_file():
                body = path.read_text(encoding="utf-8")
                assert "Kapardhi" not in body, path.name
                assert "kapardhi" not in body.lower(), path.name
