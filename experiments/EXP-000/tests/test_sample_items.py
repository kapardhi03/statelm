"""Sampler tests on fabricated scrubbed conversations.

The assertions that matter most are the ones about what is *absent* from the sheets: no label,
no value, no cue, nothing that could prime an annotator.
"""

from __future__ import annotations

import ast
import csv
import hashlib
import io
import itertools
import json
import re
import shutil
from pathlib import Path

import pytest

import cues
import diagnostics
import provenance
import safety
import sample_items
import thresholds

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


def tmp_runs_root(out):
    """A sibling of the annotation output, so no test can write into the repo's runs/.

    Passed on every invocation: the production default is the real `runs/EXP-000/`, and a test
    that forgot it would leave a run directory in the working tree.
    """
    return Path(out).parent / "runs"


def run(source, out, fields, *extra):
    buffer = io.StringIO()
    runs = tmp_runs_root(out)
    code = sample_items.main(
        ["--input", str(source), "--output", str(out), "--fields", str(fields),
         "--runs-root", str(runs), *extra],
        out=buffer, runs_root=runs)
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
        assert "SPEAKER_" not in row["context"]
        assert any(line.startswith(("customer:", "seller:"))
                   for line in row["context"].splitlines())
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
                        "speaker_role": "customer", "text": "plain statement here"}) + "\n"
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
        # `source` joined the record so exclusion can tell a real turn from a synthetic one.
        # It is still ids only: the point of this test is that no conversation text is here.
        assert payload["turns"] and all(
            set(t) == {"conversation_id", "turn_index", "source"} for t in payload["turns"])
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
                        "text": "" if i % 2 else "real text here"}) + "\n"
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
    """Each annotator gets the same items with the turn blocks in their own seeded order."""

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
        assert order["shuffle_unit"] == "turn"
        assert order["turns"] == len(set(order["turn_order"]["A"]))

    def test_the_turn_order_is_recorded_and_differs(self, workspace):
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        order = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["sheet_order"]
        assert order["turn_order"]["A"] != order["turn_order"]["B"]
        assert sorted(order["turn_order"]["A"]) == sorted(order["turn_order"]["B"])

    def test_a_turns_fields_stay_together(self, workspace):
        """The reason the unit is the turn: one context read, every question about it answered.

        Each turn must appear as exactly one contiguous run of rows, not scattered.
        """
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        for name in ("A", "B"):
            rows = read_sheet(out / f"sheet_{name}.csv")
            runs = [key for key, _ in itertools.groupby(
                rows, key=lambda r: (r["conversation_id"], r["turn_index"]))]
            assert len(runs) == len(set(runs)), f"sheet_{name} splits a turn"

    def test_the_field_order_within_a_turn_is_the_same_for_everyone(self, workspace):
        """Only the turn order varies between sheets, so fields.yaml's order is the field order."""
        source, fields, out = workspace
        run(source, out, fields, "--annotators", "A", "B")
        orders = set()
        for name in ("A", "B"):
            rows = read_sheet(out / f"sheet_{name}.csv")
            for _, group in itertools.groupby(
                    rows, key=lambda r: (r["conversation_id"], r["turn_index"])):
                orders.add(tuple(row["field"] for row in group))
        assert len(orders) == 1, orders
        assert orders.pop() == ("budget", "location_preference")

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

    def test_one_turn_cannot_be_permuted_and_says_so(self, tmp_path):
        """With a single turn there is one order, so the run reports it rather than pretending."""
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
        assert manifest["sheet_order"]["turns"] == 1
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


#: A corpus shaped like the one that voided run 20261002T175103Z-f318529: mostly seller turns,
#: short customer replies, a media placeholder. Invented text throughout.
SELLER_HEAVY = [
    ("agent", "Hello! Thanks for your interest in the project."),
    ("agent", "We have 2BHK and 3BHK options, maybe I can share a brochure?"),
    ("customer", "ok"),
    ("agent", "Here are the floor plans, around 1200 sq ft each."),
    ("customer", "[media: voice note]"),
    ("agent", "Sorry, I meant the east-facing units are the available ones."),
    ("customer", "budget is around 80 lakhs, maybe a bit more"),
    ("agent", "Noted. Possession is by March."),
    ("customer", "we need a 3BHK near Kondapur actually"),
    ("agent", "I can arrange a site visit."),
    ("customer", "yes"),
    ("customer", "my wife has to decide, probably next month"),
]


def write_roled_conversations(root: Path, turns=SELLER_HEAVY, count: int = 3) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for c in range(1, count + 1):
        rows = [
            {"conversation_id": f"conv_{c:03d}", "turn_index": i, "timestamp": None,
             "timestamp_raw": "", "speaker_role": role,
             "speaker_id": "SPEAKER_1" if role == "customer" else "SPEAKER_2",
             "text": text, "provenance": {"source": "human"}}
            for i, (role, text) in enumerate(turns)
        ]
        (root / f"conv_{c:03d}.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    return root


@pytest.fixture
def seller_heavy(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed")
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


class TestOnlyCustomerTurnsAreTargets:
    """The failure that voided run 20261002T175103Z-f318529."""

    def test_every_target_is_a_customer_turn(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--annotators", "A", "B")
        for name in ("A", "B"):
            roles = {row["turn_role"] for row in read_sheet(out / f"sheet_{name}.csv")}
            assert roles == {"customer"}, roles

    def test_no_media_placeholder_is_ever_a_target(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        for row in read_sheet(out / "sheet_A.csv"):
            assert not row["turn_text"].startswith("[media:"), row["turn_text"]

    def test_no_target_is_shorter_than_the_floor(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        for row in read_sheet(out / "sheet_A.csv"):
            assert len(row["turn_text"].split()) >= thresholds.MIN_TARGET_WORDS, row["turn_text"]

    def test_seller_turns_are_still_in_the_context(self, seller_heavy):
        """They are needed there: guideline §3.3 turns on who said a thing."""
        source, fields, out = seller_heavy
        run(source, out, fields)
        contexts = "\n".join(row["context"] for row in read_sheet(out / "sheet_A.csv"))
        assert "seller:" in contexts
        assert "customer:" in contexts

    def test_media_placeholders_are_still_visible_in_the_context(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        contexts = "\n".join(row["context"] for row in read_sheet(out / "sheet_A.csv"))
        assert "[media: voice note]" in contexts

    def test_a_corpus_of_only_seller_turns_is_a_loud_error(self, tmp_path):
        source = write_roled_conversations(
            tmp_path / "scrubbed", turns=[("agent", "we have many options for you")] * 6)
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="no turn in either corpus"):
            run(source, tmp_path / "out", fields)

    def test_that_error_names_the_rejection_counts(self, tmp_path):
        source = write_roled_conversations(
            tmp_path / "scrubbed", turns=[("agent", "we have many options"), ("customer", "ok")])
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        with pytest.raises(sample_items.SamplerError) as caught:
            run(source, tmp_path / "out", fields)
        assert "not_customer" in str(caught.value)
        assert "too_short" in str(caught.value)


class TestSheetsShowRolesNotSpeakerIds:
    def test_the_column_is_turn_role(self):
        assert "turn_role" in sample_items.SHEET_COLUMNS
        assert "turn_speaker" not in sample_items.SHEET_COLUMNS

    def test_no_speaker_id_appears_anywhere_in_a_sheet(self, seller_heavy):
        """The voided run's sheets showed SPEAKER_n, which made rule §3.3 unusable."""
        source, fields, out = seller_heavy
        run(source, out, fields, "--annotators", "A", "B")
        for name in ("A", "B"):
            body = (out / f"sheet_{name}.csv").read_text(encoding="utf-8")
            assert "SPEAKER_" not in body

    def test_the_context_is_labelled_by_role_too(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        for row in read_sheet(out / "sheet_A.csv"):
            for line in row["context"].splitlines():
                assert line.split(":")[0] in {"customer", "seller"}, line


class TestTheCensusIsPrintedBeforeSheetsExist:
    def test_it_reports_totals_and_rejections(self, seller_heavy):
        source, fields, out = seller_heavy
        code, output = run(source, out, fields)
        assert code == 0
        assert "turns read: 36" in output
        assert "eligible targets" in output
        assert "not_customer" in output and "too_short" in output
        assert "media_placeholder" in output

    def test_it_reports_eligibility_per_stratum_and_per_field(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields)
        assert "eligible per stratum" in output
        assert "field mentions among eligible" in output

    def test_it_warns_when_the_corpus_cannot_supply_the_quotas(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--n-items", "400")
        assert "WARNING" in output

    def test_the_census_is_in_the_manifest(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        census = manifest["corpus_census"]
        assert census["turns_total"] == 36
        assert census["eligible_targets"] == census["turns_total"] - sum(
            census["rejected"].values())
        assert census["rejected"]["not_customer"] > 0

    def test_the_census_holds_no_conversation_text(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert "lakhs" not in json.dumps(manifest["corpus_census"])


class TestQuotas:
    def test_the_pre_registered_quotas_are_what_the_sampler_uses(self):
        assert sample_items.DEFAULT_QUOTAS == dict(thresholds.SAMPLING_QUOTAS)
        assert sample_items.DEFAULT_QUOTAS == {
            "field_mention": 0.4, "correction": 0.2, "hedge": 0.2, "random": 0.2}

    def test_random_is_the_remainder_not_a_cue(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        enrichment = manifest["enrichment"]
        assert "random" in enrichment["targets"]
        # Every eligible turn is available to the random remainder, cue or not.
        assert enrichment["eligible_per_stratum"]["random"] >= \
            enrichment["eligible_per_stratum"]["field_mention"]

    def test_a_shortfall_is_reported_per_stratum(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--n-items", "200")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert any(manifest["enrichment"]["shortfall"].values())
        assert "shortfall" in output

    def test_multi_speaker_has_no_quota_but_is_still_reported(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert "multi_speaker" not in manifest["enrichment"]["quotas"]
        assert "multi_speaker" in manifest["corpus_census"]["by_stratum"]

    def test_the_settings_record_the_eligibility_rules(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields)
        settings = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["settings"]
        assert settings["target_roles"] == ["customer"]
        assert settings["min_target_words"] == 3
        assert settings["field_keywords_overridden"] is False


class TestFieldKeywordOverride:
    def test_a_local_file_can_add_locality_names(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        custom = tmp_path / "keywords.yaml"
        custom.write_text("field_keywords:\n  location_preference: [kondapur, gachibowli]\n",
                          encoding="utf-8")
        code, _ = run(source, out, fields, "--field-keywords", str(custom))
        assert code == 0
        settings = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["settings"]
        assert settings["field_keywords_overridden"] is True

    def test_an_unknown_field_is_an_error(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        custom = tmp_path / "bad.yaml"
        custom.write_text("field_keywords:\n  not_a_field: [x]\n", encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="not in the pilot field list"):
            run(source, out, fields, "--field-keywords", str(custom))

    def test_an_empty_file_is_an_error(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        custom = tmp_path / "empty.yaml"
        custom.write_text("field_keywords: {}\n", encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="non-empty"):
            run(source, out, fields, "--field-keywords", str(custom))


class TestTheCommittedFieldKeywordsFile:
    """field_keywords.yaml is committed, so it is part of the instrument and gets a test."""

    PATH = Path(__file__).parent.parent / "field_keywords.yaml"

    def test_it_loads(self):
        merged = sample_items.load_field_keywords(self.PATH)
        assert merged["location_preference"]

    def test_it_keeps_the_built_in_indicator_words(self):
        """The option replaces rather than merges, so dropping them would be a silent loss."""
        merged = sample_items.load_field_keywords(self.PATH)
        builtin = set(thresholds.FIELD_KEYWORDS["location_preference"])
        assert builtin <= set(merged["location_preference"]), \
            sorted(builtin - set(merged["location_preference"]))

    def test_it_leaves_the_other_fields_alone(self):
        merged = sample_items.load_field_keywords(self.PATH)
        for field, words in thresholds.FIELD_KEYWORDS.items():
            if field != "location_preference":
                assert merged[field] == words, field

    @pytest.mark.parametrize("text", [
        "anything in Gachibowli", "we like Kokapet", "flat in Nanakramguda",
        "Financial District please", "Uppal is too far", "near Hi-Tech City",
        "Shadnagar or Adibatla", "Puppalaguda side",
    ])
    def test_the_localities_the_suffix_heuristic_misses_now_match(self, text):
        merged = sample_items.load_field_keywords(self.PATH)
        assert "location_preference" in cues.fields_mentioned(text, merged), text

    def test_an_indicator_only_turn_still_matches_with_the_file_loaded(self):
        merged = sample_items.load_field_keywords(self.PATH)
        assert "location_preference" in cues.fields_mentioned(
            "somewhere near the metro", merged)

    def test_it_does_not_match_ordinary_sentences(self):
        merged = sample_items.load_field_keywords(self.PATH)
        for text in ("thanks for your time", "i will call you tomorrow"):
            assert "location_preference" not in cues.fields_mentioned(text, merged), text


SYNTHETIC_TURNS = [
    ("agent", "Hello, thanks for the enquiry about our project."),
    ("customer", "konchem flexible, around 85 lakhs anukuntunna"),
    ("agent", "Noted. Any preferred area?"),
    ("customer", "kaadu kaadu, I meant 95 lakhs"),
    ("customer", "3BHK near Kondapur would suit us"),
    ("agent", "I will share two options."),
    ("customer", "my wife has to decide finally"),
    ("customer", "possession by next Diwali maybe"),
]


@pytest.fixture
def two_sources(tmp_path):
    real = write_roled_conversations(tmp_path / "real", count=3)
    syn = write_roled_conversations(tmp_path / "syn", turns=SYNTHETIC_TURNS, count=3)
    # Rename the synthetic conversations so their ids differ, as the real sets do.
    for path in sorted(syn.glob("*.jsonl")):
        body = path.read_text(encoding="utf-8").replace("conv_", "syn_")
        path.write_text(body, encoding="utf-8")
        path.rename(syn / path.name.replace("conv_", "syn_"))
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return real, syn, fields, tmp_path / "annotation"


def run_two(real, syn, fields, out, *extra):
    buffer = io.StringIO()
    runs = tmp_runs_root(out)
    code = sample_items.main(
        ["--input", str(real), "--synthetic", str(syn), "--output", str(out),
         "--fields", str(fields), "--runs-root", str(runs), *extra],
        out=buffer, runs_root=runs)
    return code, buffer.getvalue()


class TestAllStratum:
    def test_it_takes_every_turn_in_the_stratum(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--all-stratum", "field_mention",
                        "--no-random-topup")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        census, enrichment = manifest["corpus_census"], manifest["enrichment"]
        assert enrichment["achieved"]["field_mention"] == census["by_stratum"]["field_mention"]
        assert enrichment["all_strata"] == ["field_mention"]

    def test_it_ignores_n_items_for_that_stratum(self, seller_heavy):
        """"Take every" has to win over a share of a target, or the flag means nothing."""
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--all-stratum", "field_mention",
                        "--no-random-topup", "--n-items", "5")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        eligible = manifest["corpus_census"]["by_stratum"]["field_mention"]
        assert manifest["enrichment"]["achieved"]["field_mention"] == eligible
        assert "exceeds --n-items 5" in output

    def test_no_random_topup_adds_no_cue_free_turns(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--all-stratum", "field_mention", "--no-random-topup")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["enrichment"]["achieved"]["random"] == 0
        assert manifest["enrichment"]["random_topup"] is False

    def test_an_unknown_stratum_is_rejected_by_the_parser(self, seller_heavy):
        source, fields, out = seller_heavy
        with pytest.raises(SystemExit):
            run(source, out, fields, "--all-stratum", "not_a_stratum")


class TestCensusOnly:
    def test_it_writes_no_annotation_artifact(self, seller_heavy):
        """It does write a run record now, which is the point; it writes no sheet."""
        source, fields, out = seller_heavy
        code, output = run(source, out, fields, "--census-only")
        assert code == 0
        assert not out.exists()
        assert "no annotation artifact written" in output

    def test_it_still_prints_the_census(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--census-only")
        assert "eligible targets" in output
        assert "eligible per stratum" in output


class TestTwoSources:
    def test_both_sets_contribute_items(self, two_sources):
        real, syn, fields, out = two_sources
        code, output = run_two(real, syn, fields, out, "--synthetic-turns", "4",
                               "--annotators", "A", "B")
        assert code == 0
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        by_source = manifest["items_by_source"]
        assert by_source["real"] > 0 and by_source["synthetic"] > 0

    def test_the_item_count_is_printed_before_the_sheets(self, two_sources):
        real, syn, fields, out = two_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        assert "ITEMS TO BE WRITTEN" in output
        count_at = output.index("ITEMS TO BE WRITTEN")
        sheets_at = output.index("sheets: ")
        assert count_at < sheets_at, "the count must precede the sheet line"

    def test_no_sheet_reveals_the_source(self, two_sources):
        real, syn, fields, out = two_sources
        run_two(real, syn, fields, out, "--synthetic-turns", "4", "--annotators", "A", "B")
        for name in ("A", "B"):
            body = (out / f"sheet_{name}.csv").read_text(encoding="utf-8")
            assert "source" not in body.lower()
            assert "synthetic" not in body.lower()
            assert "syn_" not in body, "the id prefix would leak the source"
            assert "conv_" not in body
            assert "source" not in read_sheet(out / f"sheet_{name}.csv")[0]

    def test_sheet_ids_are_aliases_from_one_namespace(self, two_sources):
        """A `syn_` prefix would tell an annotator the turn was model-written."""
        real, syn, fields, out = two_sources
        run_two(real, syn, fields, out, "--synthetic-turns", "4")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        alias = manifest["conversation_alias"]
        assert alias
        assert all(a.startswith("c") and a[1:].isdigit() for a in alias)
        true_ids = set(alias.values())
        assert any(t.startswith("conv_") for t in true_ids)
        assert any(t.startswith("syn_") for t in true_ids)
        shown = {row["conversation_id"] for row in read_sheet(out / "sheet_A.csv")}
        assert shown <= set(alias)

    def test_the_manifest_maps_every_item_to_a_source(self, two_sources):
        real, syn, fields, out = two_sources
        run_two(real, syn, fields, out, "--synthetic-turns", "4")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        ids = {row["item_id"] for row in read_sheet(out / "sheet_A.csv")}
        assert set(manifest["item_source"]) == ids
        assert set(manifest["item_source"].values()) == {"real", "synthetic"}

    def test_pilot_items_keep_the_true_ids(self, two_sources):
        """Test-split exclusion has to match the real corpus, not a per-run alias."""
        real, syn, fields, out = two_sources
        run_two(real, syn, fields, out, "--synthetic-turns", "4")
        pilot = json.loads((out / "pilot_items.json").read_text(encoding="utf-8"))
        ids = {t["conversation_id"] for t in pilot["turns"]}
        assert any(i.startswith("conv_") for i in ids)
        assert any(i.startswith("syn_") for i in ids)
        assert {t["source"] for t in pilot["turns"]} == {"real", "synthetic"}

    def test_a_colliding_conversation_id_is_a_loud_error(self, tmp_path):
        real = write_roled_conversations(tmp_path / "real", count=2)
        syn = write_roled_conversations(tmp_path / "syn", turns=SYNTHETIC_TURNS, count=2)
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        with pytest.raises(sample_items.SamplerError, match="appear in both"):
            run_two(real, syn, fields, tmp_path / "out")

    def test_the_synthetic_census_is_reported_separately(self, two_sources):
        real, syn, fields, out = two_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        assert "--- synthetic set:" in output
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["synthetic_census"]["source"] == "synthetic"
        assert manifest["corpus_census"]["source"] == "real"


class TestTheCommittedSyntheticSet:
    ROOT = Path(__file__).parent.parent / "synthetic"

    def conversations(self):
        return sorted(self.ROOT.glob("*.jsonl"))

    def rows(self):
        return [json.loads(line) for path in self.conversations()
                for line in path.read_text(encoding="utf-8").splitlines() if line]

    def test_there_are_twenty_conversations(self):
        assert len(self.conversations()) == 20

    def test_every_record_is_marked_synthetic_with_its_generator(self):
        for row in self.rows():
            assert row["provenance"]["source"] == "synthetic"
            assert row["provenance"]["generator"] == "claude-opus-5"
            assert row["provenance"]["labeler"] is None

    def test_it_carries_no_labels_and_no_hints(self):
        """Not in the text, not in a sidecar, not in a filename."""
        texts = " ".join(row["text"] for row in self.rows()).lower()
        for token in ("no-op", "abstain", "hedged", "intended", "stratum", "this turn tests"):
            assert token not in texts, token
        for path in self.conversations():
            assert path.stem.startswith("syn_") and path.stem[4:].isdigit(), path.name

    def test_no_phenomenon_is_clustered_in_one_conversation(self):
        """One phenomenon per file would label by position as surely as a column would."""
        carrying = {"hedge": set(), "correction": set(), "field": set()}
        for row in self.rows():
            if row["speaker_role"] != "customer":
                continue
            cid, text = row["conversation_id"], row["text"]
            if cues.has_hedge_cue(text):
                carrying["hedge"].add(cid)
            if cues.has_correction_cue(text):
                carrying["correction"].add(cid)
            if cues.fields_mentioned(text):
                carrying["field"].add(cid)
        for name, conversations in carrying.items():
            assert len(conversations) >= 3, (name, sorted(conversations))

    def test_it_contains_code_mixed_material(self):
        hits = sum(1 for row in self.rows() if cues.has_code_mixed_cue(row["text"]))
        assert hits >= 5, hits

    def test_it_has_both_roles_and_enough_eligible_targets(self):
        rows = self.rows()
        roles = {row["speaker_role"] for row in rows}
        assert roles == {"customer", "agent"}
        eligible = sum(1 for row in rows if cues.is_eligible_target(row))
        assert eligible >= 16, eligible

    def test_the_readme_states_the_limit_without_mapping_phenomena(self):
        readme = (self.ROOT / "README.md").read_text(encoding="utf-8")
        assert "not evidence for ADR-003" in readme
        assert "Do not read the conversations before labelling" in readme
        # Naming the id range while describing the file-naming scheme is fine. What must not
        # happen is a conversation id appearing alongside a phenomenon, which would map one to
        # the other and prime the annotator as surely as a label would.
        phenomena = ("hedge", "correction", "conflict", "ambiguous", "vague", "unit",
                     "code-mix", "approximation")
        ids = {row["conversation_id"] for row in self.rows()}
        for line in readme.splitlines():
            lowered = line.lower()
            named = [cid for cid in ids if cid in line]
            if named and any(word in lowered for word in phenomena):
                raise AssertionError(f"README maps {named} to a phenomenon: {line!r}")


#: Hedges and corrections carried ONLY by romanized Telugu and Hindi forms. No English cue
#: appears in any turn: not "flexible", not "maybe", not "actually", not "sorry". A census run
#: against the pre-2026-10-03 lists would score every one of these turns "plain".
CODE_MIXED_ONLY = [
    ("agent", "Good morning, sharing the brochure now."),
    ("customer", "budget konchem ekkuva avthundi"),
    ("agent", "Understood, noted."),
    ("customer", "kaadu, 95 lakhs ani cheppanu"),
    ("customer", "price gurinchi alochistanu ippudu"),
    ("agent", "Please take your time."),
    ("customer", "nahi nahi, 3BHK kavali ante"),
    ("customer", "possession date pata nahi inka"),
]

#: The same turns with the romanized cue words removed and nothing else changed. The control
#: for the fixture above: it pins that what the census counts comes from the cue lists, not
#: from some other property these turns happen to share.
ENGLISH_BLIND = [
    ("agent", "Good morning, sharing the brochure now."),
    ("customer", "budget ekkuva avthundi ippudu"),
    ("agent", "Understood, noted."),
    ("customer", "95 lakhs ani cheppanu nenu"),
    ("customer", "price gurinchi cheppandi ippudu"),
    ("agent", "Please take your time."),
    ("customer", "3BHK kavali ante inka"),
    ("customer", "possession date cheppandi inka"),
]


def census_strata(text, header="eligible per stratum: "):
    """The `{stratum: count}` dict the census printed, or {} if it printed none."""
    for line in text.splitlines():
        if line.startswith(header):
            return ast.literal_eval(line[len(header):].strip())
    return {}


def nonzero(counts):
    """A census dict as the sampler prints it: zero-valued strata are filtered out."""
    return {k: v for k, v in counts.items() if v}


def stratum_dicts(output):
    """Every `{stratum: count}` mapping the run printed, in the order printed."""
    names = set(cues.STRATA) | {thresholds.RANDOM_STRATUM}
    found = []
    for line in output.splitlines():
        start, end = line.find("{"), line.rfind("}")
        if start == -1 or end < start:
            continue
        try:
            value = ast.literal_eval(line[start:end + 1])
        except (ValueError, SyntaxError):
            continue
        if isinstance(value, dict) and names & set(value):
            found.append(value)
    return found


def census_total(text, prefix):
    """The integer a census line ends with, e.g. `turns read: 24`."""
    for line in text.splitlines():
        if line.startswith(prefix):
            return int(line.rsplit(":", 1)[1].strip())
    raise AssertionError(f"no census line starting {prefix!r} in {text!r}")


def synthetic_census_section(output):
    """Just the synthetic set's census block: header to the item count that follows it."""
    _, marker, tail = output.partition("--- synthetic set:")
    assert marker, "no synthetic census in this output"
    section, _, _ = tail.partition("ITEMS TO BE WRITTEN")
    return section


@pytest.fixture
def code_mixed_only(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed", turns=CODE_MIXED_ONLY, count=3)
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


@pytest.fixture
def english_blind(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed", turns=ENGLISH_BLIND, count=3)
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


class TestCensusOnlyUsesTheExtendedCueLists:
    """`--census-only` counts strata with the same cue lists a sampling run uses.

    This is the test to cite for "did the v3 census read the romanized forms". `--census-only`
    shares one code path with a sampling run -- `candidate_turns` -> `cues.strata_for` -> the
    module-level cue tuples -- and returns only after `report_census`, so there is no way for
    the two to disagree. These tests pin that end to end rather than by inspection.
    """

    def test_it_counts_hedges_and_corrections_carried_only_by_romanized_forms(
            self, code_mixed_only):
        source, fields, out = code_mixed_only
        code, output = run(source, out, fields, "--census-only")
        assert code == 0
        strata = census_strata(output)
        # 3 conversations x 3 romanized hedges and 2 romanized corrections.
        assert strata.get("hedge") == 9, output
        assert strata.get("correction") == 6, output
        assert "matched a code-mixed cue" in output

    def test_the_same_turns_without_those_words_count_zero(self, english_blind):
        """Sensitivity: the counts above come from the cue lists, not from the fixture."""
        source, fields, out = english_blind
        _, output = run(source, out, fields, "--census-only")
        strata = census_strata(output)
        assert strata.get("hedge", 0) == 0, output
        assert strata.get("correction", 0) == 0, output
        assert "matched a code-mixed cue" not in output


@pytest.fixture
def mixed_sources(tmp_path):
    """A real set with no hedge or correction, and a synthetic set with 6 and 4 of them.

    The two sets hold different numbers of conversations on purpose. A test that looks for a
    leaked synthetic figure can only tell a leak from a coincidence if the two sets' stratum
    counts differ, and an earlier version of this fixture gave both `field_mention: 15`.
    """
    real = write_roled_conversations(tmp_path / "real", turns=ENGLISH_BLIND, count=3)
    syn = write_roled_conversations(tmp_path / "syn", turns=CODE_MIXED_ONLY, count=2)
    for path in sorted(syn.glob("*.jsonl")):
        body = path.read_text(encoding="utf-8").replace("conv_", "syn_")
        path.write_text(body, encoding="utf-8")
        path.rename(syn / path.name.replace("conv_", "syn_"))
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return real, syn, fields, tmp_path / "annotation"


class TestSyntheticStrataAreWithheld:
    """Totals only for a `--synthetic` set, unless the operator asks for more.

    Kapardhi, 2026-10-03: the v3 sampling run printed the synthetic set's stratum counts to
    Annotator A's terminal before labelling. Nothing item-level was shown and Annotator B saw
    nothing, so no label is known to be affected, but "hedge 13" tells an annotator how many
    hedges to find in the part of the item set that holds them.
    """

    def test_the_synthetic_census_prints_no_stratum_counts(self, mixed_sources):
        real, syn, fields, out = mixed_sources
        code, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        assert code == 0
        section = synthetic_census_section(output)
        assert "eligible per stratum" not in section, section
        assert "field mentions among eligible" not in section, section
        assert "matched a code-mixed cue" not in section, section
        assert "per-stratum counts withheld" in section

    def test_the_real_census_still_prints_its_strata(self, mixed_sources):
        """The suppression is for the synthetic set. The real census IS the research finding."""
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        head, _, _ = output.partition("--- synthetic set:")
        assert "eligible per stratum" in head
        assert census_strata(head).get("field_mention", 0) > 0

    def test_the_synthetic_phenomenon_counts_do_not_reach_the_terminal(self, mixed_sources):
        """Neither count can be read off the output, directly or by coincidence.

        The real set has no hedge and no correction, so a printed 6 or 4 beside either name
        could only have come from the synthetic census.
        """
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        by_stratum = manifest["synthetic_census"]["by_stratum"]
        assert by_stratum.get("hedge") == 6 and by_stratum.get("correction") == 4, by_stratum
        for stratum in ("hedge", "correction"):
            assert f"'{stratum}': {by_stratum[stratum]}" not in output, stratum

    def test_every_stratum_breakdown_printed_is_a_real_set_figure(self, mixed_sources):
        """Stronger than a string search: each printed breakdown is attributable to the real set.

        A coincidence is then not a failure, because the figure is a real one either way. This
        covers the printed numbers only. The sampling quotas are pre-registered and public, so
        an expected composition stays derivable from `thresholds.SAMPLING_QUOTAS` and the turn
        count; that is a limit of the design, not something a flag can close.
        """
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        real_figures = [nonzero(manifest["corpus_census"]["by_stratum"]),
                        manifest["enrichment"]["achieved"],
                        nonzero(manifest["enrichment"]["achieved"]),
                        manifest["enrichment"]["shortfall"],
                        nonzero(manifest["enrichment"]["shortfall"])]
        synthetic = nonzero(manifest["synthetic_census"]["by_stratum"])
        assert synthetic not in real_figures, "fixture cannot distinguish the two sets"
        printed = stratum_dicts(output)
        assert printed, output
        for breakdown in printed:
            assert breakdown in real_figures, breakdown

    def test_synthetic_enrichment_is_reported_as_a_total(self, mixed_sources):
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4")
        assert "synthetic enrichment achieved" not in output
        assert "synthetic enrichment: 4 turn(s) sampled" in output

    def test_the_flag_prints_them_again(self, mixed_sources):
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4",
                            "--show-synthetic-strata")
        section = synthetic_census_section(output)
        assert census_strata(section).get("hedge") == 6, section
        assert "synthetic enrichment achieved" in output

    def test_the_counts_are_in_the_manifest_either_way(self, mixed_sources):
        """Withheld from the terminal, never dropped: the record still needs them."""
        real, syn, fields, out = mixed_sources
        for extra in ((), ("--show-synthetic-strata",)):
            run_two(real, syn, fields, out, "--synthetic-turns", "4", *extra)
            manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
            assert manifest["synthetic_census"]["by_stratum"]["hedge"] == 6
            assert manifest["synthetic_enrichment"]["achieved"]

    def test_the_manifest_records_whether_they_were_printed(self, mixed_sources):
        """So a run can be audited for the exposure, not just fixed going forward."""
        real, syn, fields, out = mixed_sources
        run_two(real, syn, fields, out, "--synthetic-turns", "4")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["settings"]["synthetic_strata_printed"] is False
        run_two(real, syn, fields, out, "--synthetic-turns", "4", "--show-synthetic-strata")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["settings"]["synthetic_strata_printed"] is True

    def test_a_real_only_run_records_no_exposure(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--show-synthetic-strata")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["settings"]["synthetic_strata_printed"] is False


class TestTheOvershootMessageNamesTheRightCause:
    """`--n-items` governs `--input`; `--synthetic-turns` adds to it.

    The message used to name `--all-stratum` for every overshoot, printing an empty stratum
    list when none was asked for, which reads as a bug in the flag rather than as the sum of
    two requests.
    """

    def test_a_synthetic_set_is_named_as_the_cause(self, mixed_sources):
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--synthetic-turns", "4", "--n-items", "20")
        assert "--synthetic-turns 4 adds to it" in output
        assert "--all-stratum" not in output

    def test_all_stratum_is_still_named_when_it_is_the_cause(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--all-stratum", "field_mention",
                        "--no-random-topup", "--n-items", "5")
        assert "--all-stratum takes every turn in ['field_mention']" in output
        assert "--synthetic-turns" not in output


class TestCensusOnlyMatchesASamplingRun:
    """`--census-only` and a sampling run report the same census on the same corpus.

    They share one code path, so they cannot differ — which is the point. The experiment record
    cites the equivalence when it says the v3 census read the extended cue lists, and a cited
    equivalence should be pinned by a test rather than argued from reading the code.
    """

    def test_the_census_block_is_identical(self, code_mixed_only):
        source, fields, out = code_mixed_only
        _, census_only = run(source, out, fields, "--census-only")
        assert not out.exists(), "--census-only must write nothing before the comparison"
        _, sampling = run(source, out, fields)
        assert census_only.partition("\n\n")[0] == sampling.partition("\n\n")[0]

    def test_it_matches_the_census_the_sampling_run_recorded(self, code_mixed_only):
        """Printed against stored: the manifest is what every later analysis reads."""
        source, fields, out = code_mixed_only
        _, census_only = run(source, out, fields, "--census-only")
        run(source, out, fields)
        recorded = json.loads((out / "manifest.json").read_text(encoding="utf-8"))["corpus_census"]
        assert census_strata(census_only) == nonzero(recorded["by_stratum"])
        assert census_strata(census_only, "field mentions among eligible: ") == \
            nonzero(recorded["field_mentions"])
        assert census_total(census_only, "turns read: ") == recorded["turns_total"]
        assert census_total(census_only, "eligible targets ") == recorded["eligible_targets"]
        # The romanized forms are why this fixture has any hedge or correction at all.
        assert recorded["by_stratum"]["hedge"] == 9
        assert recorded["by_stratum"]["correction"] == 6
        assert recorded["code_mixed_cue_hits"] == 15


#: Telugu script (U+0C00-U+0C7F). Nothing in either cue list can match these: every cue is an
#: ASCII string, and a romanized form is a different sequence of codepoints from the native
#: spelling of the same word.
TELUGU_TURNS = [
    ("agent", "Good morning, sharing the brochure now."),
    ("customer", "బడ్జెట్ కొంచెం ఎక్కువ అవుతుంది"),
    ("agent", "Understood, noted."),
    ("customer", "ఇల్లు కావాలి ఇప్పుడే"),
    ("customer", "మూడు పడక గదులు కావాలి"),
    ("agent", "Please take your time."),
    ("customer", "ధర గురించి ఆలోచిస్తాను"),
    ("customer", "వచ్చే నెల చూద్దాం"),
]

#: Devanagari (U+0900-U+097F), and the decisive case. "थोड़ा" is the native spelling of "thoda"
#: and "नहीं नहीं" of "nahi nahi" -- both already in the cue lists, both in their romanized ASCII
#: form. So these two turns carry a hedge and a correction that the lists provably cannot see.
DEVANAGARI_TURNS = [
    ("agent", "Sharing two options now."),
    ("customer", "बजट थोड़ा ज्यादा है"),
    ("customer", "नहीं नहीं तीन कमरे"),
    ("agent", "Noted, thank you."),
    ("customer", "अगले महीने देखते हैं"),
]

#: Keys whose values are run metadata rather than anything measured. Every other string value
#: in a run record has to be a cue, a keyword, a field name or a script label.
METADATA_KEYS = frozenset({
    "git_commit", "platform", "python", "run_id", "input_dir", "sha256",
    "model_name", "model_revision", "prompt_template_hash",
})


@pytest.fixture
def telugu_corpus(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed", turns=TELUGU_TURNS, count=3)
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


@pytest.fixture
def devanagari_corpus(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed", turns=DEVANAGARI_TURNS, count=2)
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


def only_run_dir(out):
    """The single run directory the invocation created, under the tmp runs root."""
    runs = tmp_runs_root(out)
    dirs = sorted(path for path in runs.iterdir() if path.is_dir())
    assert len(dirs) == 1, dirs
    return dirs[0]


def read_record(out, name):
    return json.loads((only_run_dir(out) / f"{name}.json").read_text(encoding="utf-8"))


def walk_strings(node, key=None):
    """Every (key, string) pair in a JSON tree, so a test can check values and keys apart."""
    if isinstance(node, dict):
        for child_key, value in node.items():
            yield None, child_key
            yield from walk_strings(value, child_key)
    elif isinstance(node, list):
        for value in node:
            yield from walk_strings(value, key)
    elif isinstance(node, str):
        yield key, node


def allowed_strings(keywords=None):
    keyword_map = keywords if keywords is not None else thresholds.FIELD_KEYWORDS
    allowed = {*cues.CORRECTION_CUES, *cues.HEDGE_CUES, *cues.CODE_MIXED_CUES}
    allowed |= set(diagnostics.SCRIPT_BUCKETS) | set(cues.STRATA)
    for field, words in keyword_map.items():
        allowed.add(field)
        allowed.update(words)
    allowed |= {
        "EXP-000", "census", "cue_diagnostics", "census+cue_diagnostics",
        sample_items.SOURCE_REAL, sample_items.SOURCE_SYNTHETIC,
        "amount_pattern", "locality_suffix_pattern", "unknown", "",
        diagnostics.NO_CUE_NOTE, sample_items.SYNTHETIC_CENSUS_NOTE,
        diagnostics.KEYWORD_SOURCE_BUILT_IN, diagnostics.KEYWORD_SOURCE_FILE,
        diagnostics.FLOOR_NOTE, diagnostics.FLOOR_POPULATION,
        *thresholds.TARGET_ROLES,
    }
    return allowed


class TestCueDiagnostics:
    """Can the cue lists fire on this corpus at all?

    The v3 census could not answer it: 0 matches is consistent with an absent phenomenon and
    with a probe that cannot match the text, and the census reports only the stratum totals
    those two produce identically.
    """

    def test_every_cue_is_reported_including_the_zeros(self, seller_heavy):
        source, fields, out = seller_heavy
        code, _ = run(source, out, fields, "--cue-diagnostics")
        assert code == 0
        report = read_record(out, "cue_diagnostics")
        assert set(report["cues"]["hedge"]) == set(cues.HEDGE_CUES)
        assert set(report["cues"]["correction"]) == set(cues.CORRECTION_CUES)
        assert 0 in report["cues"]["hedge"].values(), "zeros are the point of this report"
        assert all(isinstance(count, int) for count in report["cues"]["hedge"].values())

    def test_it_fires_on_an_english_corpus(self, seller_heavy):
        """Sensitivity. A diagnostic that reports zero everywhere proves nothing."""
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--cue-diagnostics")
        report = read_record(out, "cue_diagnostics")
        assert report["no_cue_matched"] is False
        assert report["cue_forms_that_matched"]["hedge"], report["cues"]["hedge"]
        assert diagnostics.NO_CUE_NOTE not in output

    def test_a_native_script_corpus_defeats_every_cue(self, telugu_corpus):
        source, fields, out = telugu_corpus
        _, output = run(source, out, fields, "--cue-diagnostics")
        report = read_record(out, "cue_diagnostics")
        assert report["no_cue_matched"] is True
        assert sum(report["cues"]["hedge"].values()) == 0
        assert sum(report["cues"]["correction"].values()) == 0
        script = report["script"]["eligible_targets"]
        assert script["counts"]["telugu"] == script["texts"] > 0
        assert script["counts"]["ascii_only"] == 0
        assert script["shares"]["telugu"] == 1.0
        assert "written in a non-ASCII script" in output

    def test_a_hedge_in_native_script_is_invisible_to_the_romanized_list(
            self, devanagari_corpus):
        """The distinction the whole diagnostic exists to draw.

        This corpus contains a hedge and a correction whose romanized spellings are both in the
        cue lists. Every cue still scores zero, so a zero here cannot mean the phenomenon is
        absent -- which is exactly the reading the v3 census could not rule out.
        """
        source, fields, out = devanagari_corpus
        _, output = run(source, out, fields, "--cue-diagnostics")
        report = read_record(out, "cue_diagnostics")
        assert report["cues"]["hedge"]["thoda"] == 0
        assert report["cues"]["correction"]["nahi nahi"] == 0
        assert report["cues"]["hedge"]["dekhte hain"] == 0
        assert report["no_cue_matched"] is True
        assert report["script"]["eligible_targets"]["counts"]["devanagari"] > 0
        assert diagnostics.NO_CUE_NOTE in output

    def test_field_keywords_and_patterns_are_reported(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--cue-diagnostics")
        report = read_record(out, "cue_diagnostics")
        assert set(report["field_keywords"]) == set(thresholds.FIELD_KEYWORDS)
        for field, words in thresholds.FIELD_KEYWORDS.items():
            entry = report["field_keywords"][field]
            assert entry["source"] == diagnostics.KEYWORD_SOURCE_BUILT_IN
            assert set(entry["hits"]) == set(words)
        # An amount pattern is how a budget is usually written, so keyword zeros beside a
        # non-zero field_mention stratum is the expected shape, not a contradiction.
        assert report["field_patterns"]["amount_pattern"] > 0

    def test_the_probe_strings_own_script_is_recorded(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--cue-diagnostics")
        script = read_record(out, "cue_diagnostics")["script"]
        for name in ("cue_strings", "field_keyword_strings"):
            profile = script[name]
            assert profile["counts"]["ascii_only"] == profile["texts"] > 0, name

    def test_it_writes_no_annotation_artifact(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--cue-diagnostics")
        assert not out.exists()
        assert "no annotation artifact written" in output
        assert sorted(path.name for path in only_run_dir(out).iterdir()) == \
            ["config.json", "cue_diagnostics.json"]

    def test_the_synthetic_set_is_excluded_by_construction(self, mixed_sources):
        """Diagnosing the real corpus must not print the synthetic set's phenomenon mix."""
        real, syn, fields, out = mixed_sources
        _, output = run_two(real, syn, fields, out, "--cue-diagnostics")
        report = read_record(out, "cue_diagnostics")
        assert "the synthetic set is excluded" in output
        # The synthetic set holds 6 romanized hedges; the real set holds none.
        assert report["no_cue_matched"] is True
        assert report["eligible_targets"] == 15


class TestRunRecordProvenance:
    """What ties a count to a commit and a corpus, which the v2 and v3 censuses had not."""

    def test_the_record_names_a_commit_and_a_corpus_hash(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only")
        config = read_record(out, "config")
        assert config["experiment"] == "EXP-000"
        assert config["step"] == "census"
        assert config["git_commit"]
        assert config["inputs"]["corpus"]["files"] == 3
        assert len(config["inputs"]["corpus"]["sha256"]) == 64
        assert config["probe"]["sha256"]
        assert config["model_name"] is None, "no model runs in this step; null, not missing"

    def test_the_corpus_hash_moves_when_the_corpus_does(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only", "--run-id", "first")
        before = read_record(out, "config")["inputs"]["corpus"]
        extra = source / "conv_004.jsonl"
        extra.write_text((source / "conv_001.jsonl").read_text(encoding="utf-8")
                         .replace("conv_001", "conv_004"), encoding="utf-8")
        shutil.rmtree(tmp_runs_root(out))
        run(source, out, fields, "--census-only", "--run-id", "second")
        after = read_record(out, "config")["inputs"]["corpus"]
        assert after["files"] == before["files"] + 1
        assert after["sha256"] != before["sha256"]

    def test_the_probe_fingerprint_moves_when_the_keywords_do(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only")
        before = read_record(out, "config")["probe"]["sha256"]
        keywords = tmp_path / "kw.yaml"
        keywords.write_text("field_keywords:\n  budget:\n    - budget\n    - bajet\n",
                            encoding="utf-8")
        shutil.rmtree(tmp_runs_root(out))
        run(source, out, fields, "--census-only", "--field-keywords", str(keywords))
        assert read_record(out, "config")["probe"]["sha256"] != before

    def test_the_census_record_holds_the_census_that_was_printed(self, seller_heavy):
        source, fields, out = seller_heavy
        _, output = run(source, out, fields, "--census-only")
        recorded = read_record(out, "census")["census"]
        assert census_strata(output) == nonzero(recorded["by_stratum"])
        assert census_total(output, "turns read: ") == recorded["turns_total"]

    def test_the_synthetic_census_is_kept_out_of_the_record(self, mixed_sources):
        """Its per-stratum counts are what Annotator A must not see; runs/ is partly tracked."""
        real, syn, fields, out = mixed_sources
        run_two(real, syn, fields, out, "--census-only")
        record = read_record(out, "census")
        assert record["source"] == sample_items.SOURCE_REAL
        assert record["synthetic_set_present"] is True
        content = (only_run_dir(out) / "census.json").read_text(encoding="utf-8")
        for stratum in ("hedge", "correction"):
            assert f'"{stratum}": 6' not in content and f'"{stratum}": 4' not in content

    def test_both_steps_share_one_run_directory(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        assert sorted(path.name for path in only_run_dir(out).iterdir()) == \
            ["census.json", "config.json", "cue_diagnostics.json"]
        assert read_record(out, "config")["step"] == "census+cue_diagnostics"

    def test_a_runs_root_outside_runs_is_refused(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        elsewhere = tmp_path / "not_runs"
        with pytest.raises(safety.OutsideOutputRoot):
            sample_items.main(
                ["--input", str(source), "--output", str(out), "--fields", str(fields),
                 "--runs-root", str(elsewhere), "--census-only"],
                out=io.StringIO(), runs_root=tmp_runs_root(out))
        assert not elsewhere.exists()


class TestRunRecordsCarryNoText:
    """Counts only. Every string value is a cue, a keyword, a field name or a script label."""

    def test_no_corpus_text_reaches_a_record(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        allowed = allowed_strings()
        for name in ("config", "census", "cue_diagnostics"):
            record = read_record(out, name)
            for key, value in walk_strings(record):
                if key in METADATA_KEYS:
                    continue
                if key is None:                      # a dict key, authored in our source
                    assert value in allowed or re.fullmatch(r"[a-z0-9_]+", value), value
                    continue
                assert value in allowed, f"{name}.json: unexpected string {value!r} at {key!r}"

    def test_a_native_script_record_holds_no_non_ascii(self, telugu_corpus):
        """The sharpest version: if any turn text leaked, the file would not be ASCII."""
        source, fields, out = telugu_corpus
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        for path in sorted(only_run_dir(out).iterdir()):
            path.read_bytes().decode("ascii")  # raises if a Telugu codepoint reached the file

    def test_no_conversation_id_reaches_a_record(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        for path in sorted(only_run_dir(out).iterdir()):
            content = path.read_text(encoding="utf-8")
            assert "conv_001" not in content, path.name
            assert "SPEAKER_" not in content, path.name


class TestLocalKeywordNamesStayLocal:
    """`--field-keywords` holds locality names this repository cannot enumerate.

    `runs/**/cue_diagnostics.json` is tracked by git, so naming an overridden field's keywords
    in it would publish exactly what that file exists to keep local. The counts still have to
    be there: whether a keyword ever fired is the diagnostic.
    """

    @staticmethod
    def local_keywords(tmp_path):
        path = tmp_path / "local_keywords.yaml"
        path.write_text("field_keywords:\n"
                        "  location_preference:\n"
                        "    - Nowherabad\n"
                        "    - Someplacepuram\n"
                        "    - Thirdnagar\n", encoding="utf-8")
        return path

    def test_an_overridden_fields_keywords_are_not_named(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        keywords = self.local_keywords(tmp_path)
        run(source, out, fields, "--cue-diagnostics", "--field-keywords", str(keywords))
        entry = read_record(out, "cue_diagnostics")["field_keywords"]["location_preference"]
        assert entry["source"] == diagnostics.KEYWORD_SOURCE_FILE
        assert entry["forms"] == 3
        assert len(entry["hits_in_file_order"]) == 3
        assert "hits" not in entry
        for path in sorted(only_run_dir(out).iterdir()):
            content = path.read_text(encoding="utf-8")
            for name in ("Nowherabad", "Someplacepuram", "Thirdnagar"):
                assert name not in content, f"{path.name} names {name}"

    def test_the_counts_are_still_there_and_in_file_order(self, tmp_path):
        """Order is how the researcher reads them against his own file, so it must be the file's."""
        turns = [("agent", "Options attached."),
                 ("customer", "Thirdnagar would suit us best"),
                 ("customer", "Thirdnagar or nearby please")]
        source = write_roled_conversations(tmp_path / "scrubbed", turns=turns, count=1)
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        out = tmp_path / "annotation"
        run(source, out, fields, "--cue-diagnostics",
            "--field-keywords", str(self.local_keywords(tmp_path)))
        entry = read_record(out, "cue_diagnostics")["field_keywords"]["location_preference"]
        assert entry["hits_in_file_order"] == [0, 0, 2], entry

    def test_a_field_left_alone_keeps_its_names(self, seller_heavy, tmp_path):
        """Only the overridden field is redacted; the built-in lists are repository content."""
        source, fields, out = seller_heavy
        run(source, out, fields, "--cue-diagnostics",
            "--field-keywords", str(self.local_keywords(tmp_path)))
        report = read_record(out, "cue_diagnostics")["field_keywords"]
        assert report["budget"]["source"] == diagnostics.KEYWORD_SOURCE_BUILT_IN
        assert set(report["budget"]["hits"]) == set(thresholds.FIELD_KEYWORDS["budget"])

    def test_the_probe_digest_names_nothing_either(self, seller_heavy, tmp_path):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only",
            "--field-keywords", str(self.local_keywords(tmp_path)))
        probe = read_record(out, "config")["probe"]
        assert probe["field_keyword_forms"]["location_preference"] == 3
        assert len(probe["sha256"]) == 64
        assert "Thirdnagar" not in json.dumps(read_record(out, "config"))


class TestNoMachineLayoutInARunRecord:
    """`config.json` is tracked. An absolute input path is a home directory."""

    def test_an_outside_input_path_is_recorded_by_name_only(self, seller_heavy):
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only")
        recorded = read_record(out, "config")["inputs"]["input_dir"]
        assert recorded == "scrubbed", recorded
        assert str(source.parent) not in json.dumps(read_record(out, "config"))

    def test_a_path_inside_the_repository_keeps_its_repo_relative_form(self):
        """The real run reads data/scrubbed/EXP-000, which is worth seeing in the record.

        Given absolutely, because a relative path resolves against the working directory here
        as it does everywhere else in the tool, and pytest's is not the repository root.
        """
        repo = Path(__file__).resolve().parents[3]
        assert provenance.repo_relative(repo / "experiments" / "EXP-000") == "experiments/EXP-000"
        assert provenance.repo_relative(repo / "data" / "scrubbed" / "EXP-000") == \
            "data/scrubbed/EXP-000"
        assert provenance.repo_relative("/tmp/somewhere/else/scrubbed") == "scrubbed"


#: English words with a rupee sign (U+20B9). Non-ASCII by character, fully matchable by word.
#: In a WhatsApp property corpus this is the common shape, not a corner case.
RUPEE_TURNS = [
    ("agent", "Sharing the price list."),
    ("customer", "budget is around ₹80 lakhs"),
    ("customer", "maybe ₹95 lakhs with parking"),
    ("agent", "Noted, thank you."),
    ("customer", "actually make it ₹85 lakhs"),
]


class TestNonAsciiBySymbolIsNotNonAsciiByScript:
    """A currency sign puts no word out of an ASCII cue list's reach.

    The first version of `report_diagnostics` summed every non-ASCII bucket and said no ASCII
    cue could match those turns. For "budget is around ₹80 lakhs" that is false twice over: the
    hedge cue "around" matches it, and the only non-ASCII character is a symbol.
    """

    def test_a_currency_sign_alone_does_not_count_as_non_ascii_letters(self):
        text = "budget is around ₹80 lakhs"
        assert diagnostics.scripts_of(text) == frozenset({"other_non_ascii"})
        assert diagnostics.has_non_ascii_letter(text) is False
        assert cues.has_hedge_cue(text) is True, "the cue the old warning denied could match"

    def test_native_script_does_count(self):
        assert diagnostics.has_non_ascii_letter("బడ్జెట్ కొంచెం ఎక్కువ") is True
        assert diagnostics.has_non_ascii_letter("बजट थोड़ा ज्यादा है") is True

    def test_the_profile_splits_the_other_bucket(self):
        profile = diagnostics.script_profile(["around ₹80 lakhs", "plain english here",
                                              "mixed ₹ and కొంచెం"])
        assert profile["counts"]["other_non_ascii"] == 2
        assert profile["other_non_ascii_detail"] == {"with_non_ascii_letter": 1,
                                                     "symbols_only": 1}
        assert profile["with_non_ascii_letters"] == 1

    def test_the_unmatchable_warning_is_not_printed_for_symbols(self, tmp_path):
        """The warning is about words in another script, so a symbol must not trigger it."""
        source = write_roled_conversations(tmp_path / "scrubbed", turns=RUPEE_TURNS, count=2)
        fields = tmp_path / "fields.yaml"
        fields.write_text(FIELDS, encoding="utf-8")
        out = tmp_path / "annotation"
        _, output = run(source, out, fields, "--cue-diagnostics")
        assert "written in a non-ASCII script" not in output
        assert "non-ASCII by symbol only" in output
        report = read_record(out, "cue_diagnostics")
        assert report["script"]["eligible_targets"]["with_non_ascii_letters"] == 0
        assert report["no_cue_matched"] is False, "these turns do hedge, in English"

    def test_the_warning_is_printed_for_native_script(self, telugu_corpus):
        source, fields, out = telugu_corpus
        _, output = run(source, out, fields, "--cue-diagnostics")
        assert "written in a non-ASCII script" in output
        assert read_record(out, "cue_diagnostics")["script"]["eligible_targets"][
            "with_non_ascii_letters"] == 15


class TestPerCueCountsAreEntailedZeroWhenTheStratumIs:
    """Why the per-cue half of the diagnostic cannot discriminate on the v3 corpus.

    `strata_for` sets the hedge stratum iff `has_hedge_cue` matches, which is one alternation
    over the same forms `per_cue_hits` matches one at a time, over the same eligible targets. An
    alternation matches iff some alternative does, so a census stratum of 0 entails every
    per-cue count is 0. The discriminating measurements are elsewhere, and the record says so.
    """

    def test_a_zero_stratum_entails_zero_per_cue_counts(self, telugu_corpus):
        source, fields, out = telugu_corpus
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        census = read_record(out, "census")["census"]
        report = read_record(out, "cue_diagnostics")
        for stratum, cue_list in (("hedge", "hedge"), ("correction", "correction")):
            assert census["by_stratum"][stratum] == 0
            assert sum(report["cues"][cue_list].values()) == 0

    def test_a_non_zero_stratum_names_which_forms_fired(self, seller_heavy):
        """Where the per-cue half earns its place: apportioning a stratum that is not zero."""
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        census = read_record(out, "census")["census"]
        report = read_record(out, "cue_diagnostics")
        assert census["by_stratum"]["hedge"] > 0
        assert report["cue_forms_that_matched"]["hedge"]

    def test_the_field_patterns_are_the_within_corpus_positive_control(self, seller_heavy):
        """field_mention > 0 shows ASCII matching fires on this corpus, bounding the claim."""
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        census = read_record(out, "census")["census"]
        patterns = read_record(out, "cue_diagnostics")["field_patterns"]
        assert census["by_stratum"]["field_mention"] > 0
        assert sum(patterns.values()) > 0


#: Short but substantive customer answers, the case the word floor cannot distinguish from
#: noise. Each is one or two words: "50 lakhs" settles a budget, "3 BHK" a property type,
#: "maybe 60" is a hedged figure. Mixed with genuinely content-free turns and with one eligible
#: turn, so the block has something to exclude and something to keep.
SHORT_ANSWER_TURNS = [
    ("agent", "What budget are you working with?"),
    ("customer", "50 lakhs"),
    ("agent", "And the configuration?"),
    ("customer", "3 BHK"),
    ("customer", "maybe 60"),
    ("customer", "ok"),
    ("customer", "thanks"),
    ("customer", "no"),
    ("agent", "I will share two options."),
    ("customer", "we are looking at three bedrooms near the metro"),
    ("customer", "[media: voice note]"),
    ("customer", ""),
]


@pytest.fixture
def short_answers(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed", turns=SHORT_ANSWER_TURNS, count=2)
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


class TestTurnsExcludedByTheWordFloor:
    """Does the 3-word floor throw away short answers that settle a field?

    The floor was pre-registered to keep the sampler off the 2-to-16 character turns that helped
    void run 20261002T175103Z-f318529, and it cannot tell "ok" from "50 lakhs". If the excluded
    population carries field mentions and cues, the frame is part of why the corpus reads
    state-sparse -- which is a third cause the v3 census's two readings do not cover.
    """

    def test_the_population_is_customer_text_turns_only(self, short_answers):
        source, fields, out = short_answers
        run(source, out, fields, "--cue-diagnostics")
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        # 6 short customer turns per conversation x 2: 50 lakhs, 3 BHK, maybe 60, ok, thanks, no.
        assert block["turns"] == 12
        assert block["min_target_words"] == 3

    def test_seller_media_and_empty_turns_are_not_in_it(self, short_answers):
        """Each has its own rejection reason; only too_short belongs in this block."""
        source, fields, out = short_answers
        run(source, out, fields, "--census-only", "--cue-diagnostics")
        rejected = read_record(out, "census")["census"]["rejected"]
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        assert block["turns"] == rejected["too_short"]
        assert rejected["media_placeholder"] == 2 and rejected["empty"] == 2
        assert block["turns"] < sum(rejected.values())

    def test_the_word_count_distribution_covers_every_count_below_the_floor(self,
                                                                           short_answers):
        source, fields, out = short_answers
        run(source, out, fields, "--cue-diagnostics")
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        assert sorted(block["word_counts"]) == ["1", "2"], "zeros included, keys are JSON strings"
        # ok, thanks, no = 3 one-word turns per conversation; 50 lakhs, 3 BHK, maybe 60 = 3 two.
        assert block["word_counts"] == {"1": 6, "2": 6}
        assert sum(block["word_counts"].values()) == block["turns"]

    def test_it_finds_the_substantive_short_answers(self, short_answers):
        source, fields, out = short_answers
        run(source, out, fields, "--cue-diagnostics")
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        assert block["field_mentions"]["budget"] == 2, "50 lakhs, once per conversation"
        assert block["field_mentions"]["property_type"] == 2, "3 BHK"
        assert block["field_patterns"]["amount_pattern"] == 2
        assert block["with_field_mention"] == 4
        assert block["cues"]["hedge"]["maybe"] == 2
        assert block["with_hedge_or_correction_cue"] == 2

    def test_every_cue_form_is_listed_including_zeros(self, short_answers):
        source, fields, out = short_answers
        run(source, out, fields, "--cue-diagnostics")
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        assert set(block["cues"]["hedge"]) == set(cues.HEDGE_CUES)
        assert set(block["cues"]["correction"]) == set(cues.CORRECTION_CUES)
        assert block["cues"]["hedge"]["konchem"] == 0
        assert block["cue_forms_that_matched"]["correction"] == []

    def test_a_corpus_of_noise_shows_nothing_substantive(self, seller_heavy):
        """Sensitivity the other way: the block must not credit content-free turns."""
        source, fields, out = seller_heavy
        run(source, out, fields, "--cue-diagnostics")
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        assert block["with_field_mention"] == 0
        assert block["with_hedge_or_correction_cue"] == 0

    def test_it_prints_as_its_own_block_with_no_verdict(self, short_answers):
        source, fields, out = short_answers
        _, output = run(source, out, fields, "--cue-diagnostics")
        assert "customer text turns excluded by the 3-word floor" in output
        assert "excluded turns: 12 (1 word 6, 2 words 6)" in output
        assert diagnostics.FLOOR_NOTE in output
        # No threshold: the tool reports the count and does not judge it.
        head, _, tail = output.partition("customer text turns excluded")
        assert "WARNING" not in tail

    def test_it_counts_against_the_effective_keyword_lists(self, short_answers, tmp_path):
        """A locality that only a --field-keywords file knows must still be counted."""
        keywords = tmp_path / "local.yaml"
        keywords.write_text("field_keywords:\n  location_preference:\n    - gachibowli\n",
                            encoding="utf-8")
        source, fields, out = short_answers
        extra = source / "conv_003.jsonl"
        extra.write_text(json.dumps({
            "conversation_id": "conv_003", "turn_index": 0, "timestamp": None,
            "timestamp_raw": "", "speaker_role": "customer", "speaker_id": "SPEAKER_1",
            "text": "Gachibowli", "provenance": {"source": "human"}}) + "\n", encoding="utf-8")
        run(source, out, fields, "--cue-diagnostics", "--field-keywords", str(keywords))
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        assert block["field_mentions"]["location_preference"] == 1
        assert "Gachibowli" not in json.dumps(block), "per field, never per keyword"


class TestTheExcludedBlockCarriesNoText:
    """It is written to a tracked record, over the turns the sampler discards."""

    def test_only_counts_reach_the_record(self, short_answers):
        source, fields, out = short_answers
        run(source, out, fields, "--cue-diagnostics")
        block = read_record(out, "cue_diagnostics")["excluded_by_word_floor"]
        allowed = allowed_strings()
        for key, value in walk_strings(block):
            if key is None:
                assert value in allowed or re.fullmatch(r"[a-z0-9_]+", value), value
                continue
            assert value in allowed, f"unexpected string {value!r} at {key!r}"

    def test_no_short_turn_text_appears(self, short_answers):
        source, fields, out = short_answers
        run(source, out, fields, "--cue-diagnostics")
        content = (only_run_dir(out) / "cue_diagnostics.json").read_text(encoding="utf-8")
        for text in ("50 lakhs", "3 BHK", "thanks", "voice note"):
            assert text not in content, text


#: One turn per placeholder the extractor writes, plus one outside the vocabulary and one
#: ordinary short turn. Every placeholder is a customer turn, since `target_rejection` checks
#: role first and a seller turn never reaches the media branch at all.
MEDIA_KIND_TURNS = [
    ("agent", "Sharing everything now."),
    ("customer", "[media: voice note]"),
    ("customer", "[media: voice note]"),
    ("customer", "[media: image]"),
    ("customer", "[MEDIA: Video]"),
    ("customer", "[media: document]"),
    ("customer", "[media: contact card]"),
    ("customer", "[media: unsupported]"),
    ("customer", "[media: sticker]"),
    ("customer", "ok"),
    ("customer", "we want three bedrooms near the metro"),
]


@pytest.fixture
def media_kinds_corpus(tmp_path):
    source = write_roled_conversations(tmp_path / "scrubbed", turns=MEDIA_KIND_TURNS, count=2)
    fields = tmp_path / "fields.yaml"
    fields.write_text(FIELDS, encoding="utf-8")
    return source, fields, tmp_path / "annotation"


class TestMediaPlaceholderKinds:
    """The census breaks the media rejections down by kind without losing the total.

    The records had been reading all 54 rejected placeholders in the real corpus as voice notes
    while the census counted them under one `media_placeholder` total, so the share that was
    speech was a characterisation rather than a measurement. Explanation (1) in
    `knowns-unknowns.md` needs them to be speech, which is why the kind has to be a number.
    """

    def test_the_kinds_sum_to_the_rejection_total(self, media_kinds_corpus):
        """The invariant: no placeholder is dropped and none is counted twice."""
        source, fields, out = media_kinds_corpus
        run(source, out, fields, "--census-only")
        census = read_record(out, "census")["census"]
        kinds = census["media_placeholder_kinds"]
        assert sum(kinds.values()) == census["rejected"]["media_placeholder"]

    def test_the_total_is_unchanged_by_the_breakdown(self, media_kinds_corpus):
        """Old runs stay comparable: `rejected` keeps the one key it always had."""
        source, fields, out = media_kinds_corpus
        run(source, out, fields, "--census-only")
        census = read_record(out, "census")["census"]
        # 8 placeholders per conversation x 2 conversations.
        assert census["rejected"]["media_placeholder"] == 16
        assert set(census["rejected"]) == {"not_customer", "media_placeholder", "too_short"}

    def test_each_kind_is_counted_under_its_own_name(self, media_kinds_corpus):
        source, fields, out = media_kinds_corpus
        run(source, out, fields, "--census-only")
        kinds = read_record(out, "census")["census"]["media_placeholder_kinds"]
        assert kinds == {"voice": 4, "image": 2, "video": 2, "document": 2,
                         "contact": 2, "unsupported": 2, "other": 2}

    def test_every_kind_is_present_including_zeros(self, seller_heavy):
        """A kind absent from the corpus reads as 0, not as a missing key."""
        source, fields, out = seller_heavy
        run(source, out, fields, "--census-only")
        kinds = read_record(out, "census")["census"]["media_placeholder_kinds"]
        assert sorted(kinds) == sorted(thresholds.MEDIA_KINDS)
        assert all(isinstance(count, int) for count in kinds.values())

    def test_an_unknown_placeholder_is_other_not_dropped(self, media_kinds_corpus):
        """A new media type in the source schema must surface, not vanish into a total."""
        source, fields, out = media_kinds_corpus
        run(source, out, fields, "--census-only")
        census = read_record(out, "census")["census"]
        assert census["media_placeholder_kinds"]["other"] == 2
        assert sum(census["media_placeholder_kinds"].values()) == \
            census["rejected"]["media_placeholder"]

    def test_the_vocabulary_matches_what_the_extractor_writes(self):
        """The one place this can drift: extract.yaml is the only writer of these strings."""
        config = (Path(__file__).resolve().parents[1] / "extract.yaml").read_text(
            encoding="utf-8")
        for placeholder in thresholds.MEDIA_PLACEHOLDER_KINDS:
            assert f'"{placeholder}"' in config, placeholder

    def test_it_prints_the_breakdown(self, media_kinds_corpus):
        source, fields, out = media_kinds_corpus
        _, output = run(source, out, fields, "--census-only")
        assert "of the 16 media placeholder(s):" in output
        assert "voice 4" in output and "other 2" in output

    def test_a_corpus_with_no_media_prints_no_breakdown(self, code_mixed_only):
        """CODE_MIXED_ONLY holds no placeholder, so the line must be absent rather than empty.

        An earlier version of this test used a fixture that does contain a voice note, so it
        asserted nothing. Caught before this landed.
        """
        source, fields, out = code_mixed_only
        _, output = run(source, out, fields, "--census-only")
        assert "media placeholder(s):" not in output
        census = read_record(out, "census")["census"]
        assert "media_placeholder" not in census["rejected"]
        assert sum(census["media_placeholder_kinds"].values()) == 0

    def test_the_kind_counts_reach_the_tracked_record(self, media_kinds_corpus):
        """It is a count, so it belongs in census.json, which is tracked."""
        source, fields, out = media_kinds_corpus
        run(source, out, fields, "--census-only")
        content = (only_run_dir(out) / "census.json").read_text(encoding="utf-8")
        assert '"media_placeholder_kinds"' in content
        assert "[media:" not in content, "kinds are names, never the placeholder text"


def test_report_census_tolerates_a_census_without_the_kind_breakdown(capsys):
    """A census dict from before the breakdown existed must not print an empty line.

    `report_census` is handed whatever dict it is given, and an older run record lacks the key.
    """
    import io
    legacy = {"turns_total": 10, "eligible_targets": 2,
              "rejected": {"media_placeholder": 3}, "by_stratum": {}, "field_mentions": {}}
    buffer = io.StringIO()
    sample_items.report_census(legacy, n_items=4, fields=2, out=buffer)
    output = buffer.getvalue()
    assert "media_placeholder 3" in output
    assert "media placeholder(s):" not in output
