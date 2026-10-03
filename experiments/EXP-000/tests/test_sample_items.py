"""Sampler tests on fabricated scrubbed conversations.

The assertions that matter most are the ones about what is *absent* from the sheets: no label,
no value, no cue, nothing that could prime an annotator.
"""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
from pathlib import Path

import pytest

import cues
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
    code = sample_items.main(
        ["--input", str(real), "--synthetic", str(syn), "--output", str(out),
         "--fields", str(fields), *extra], out=buffer)
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
    def test_it_writes_nothing(self, seller_heavy):
        source, fields, out = seller_heavy
        code, output = run(source, out, fields, "--census-only")
        assert code == 0
        assert not out.exists()
        assert "nothing was written" in output

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
