"""End-to-end tests for agreement.py on fabricated annotation sheets.

No real conversation text appears anywhere here. Several tests plant a canary string in the
sheets and then assert it is absent from everything written under runs/, which is the check
that matters most: runs/ is partly tracked by git, and a leak there would commit client-derived
content.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
from pathlib import Path

import pytest

import agreement
import safety
import thresholds

CANARY = "FABRICATED-CANARY-TEXT"
SHEET_COLUMNS = ("item_id", "conversation_id", "turn_index", "field", "field_type",
                 "field_description", "context", "turn_speaker", "turn_text",
                 "label", "value", "notes")


def item(conversation, turn, field, label_a, label_b=None, value_a="", value_b=""):
    return {"conversation": conversation, "turn": turn, "field": field,
            "label_a": label_a, "label_b": label_b if label_b is not None else label_a,
            "value_a": value_a, "value_b": value_b}


def spread(labels, *, conversations=4, per_conversation=5, fields=("budget",)):
    """Items cycling through `labels`, spread over several conversations."""
    out, index = [], 0
    for c in range(1, conversations + 1):
        for turn in range(per_conversation):
            for field in fields:
                label = labels[index % len(labels)]
                out.append(item(f"conv_{c:03d}", turn, field, label))
                index += 1
    return out


def write_sheets(root: Path, items, *, columns=SHEET_COLUMNS,
                 names=("sheet_a.csv", "sheet_b.csv")) -> tuple[Path, Path]:
    root.mkdir(parents=True, exist_ok=True)
    paths = []
    for side, name in zip(("a", "b"), names):
        path = root / name
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(columns))
            writer.writeheader()
            for entry in items:
                row = {
                    "item_id": f"{entry['conversation']}#{entry['turn']}#{entry['field']}",
                    "conversation_id": entry["conversation"],
                    "turn_index": entry["turn"],
                    "field": entry["field"],
                    "field_type": "", "field_description": "", "context": "",
                    "turn_speaker": "SPEAKER_1", "turn_text": CANARY,
                    "label": entry[f"label_{side}"], "value": entry[f"value_{side}"],
                    "notes": "",
                }
                writer.writerow({key: row.get(key, "") for key in columns})
        paths.append(path)
    return tuple(paths)


@pytest.fixture
def workspace(tmp_path):
    return {
        "sheets": tmp_path / "sheets",
        "runs": tmp_path / "runs",
        "scrubbed": tmp_path / "scrubbed",
    }


def run(workspace, items=None, *, flag="--sheets", extra=(), paths=None, resamples=50,
        write=True, **write_kwargs):
    if write and paths is None:
        paths = write_sheets(workspace["sheets"], items, **write_kwargs)
    buffer = io.StringIO()
    code = agreement.main(
        [flag, str(paths[0]), str(paths[1]),
         "--out-root", str(workspace["runs"]),
         "--disagreements-dir", str(workspace["scrubbed"]),
         "--bootstrap", str(resamples), *extra],
        runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"], out=buffer)
    return code, buffer.getvalue()


def read_sheet(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def read_outputs(workspace):
    run_dirs = sorted(p for p in workspace["runs"].iterdir() if p.is_dir())
    assert len(run_dirs) == 1, run_dirs
    metrics = json.loads((run_dirs[0] / "metrics.json").read_text(encoding="utf-8"))
    config = json.loads((run_dirs[0] / "config.json").read_text(encoding="utf-8"))
    return metrics, config, run_dirs[0]


def read_disagreements(workspace):
    files = list(workspace["scrubbed"].glob("disagreements_*.jsonl"))
    assert len(files) == 1, files
    records = [json.loads(line) for line in
               files[0].read_text(encoding="utf-8").splitlines() if line]
    return records[0], records[1:]


# ------------------------------------------------------------------ the mode is never implicit


class TestModeLabelling:
    LABELS = ("NO-OP", "VALUE", "ABSTAIN:insufficient", "ABSTAIN:ambiguous", "HEDGED")

    def test_sheets_means_inter_annotator_everywhere(self, workspace):
        code, output = run(workspace, spread(self.LABELS), flag="--sheets")
        assert code == 0
        metrics, config, _ = read_outputs(workspace)
        header, _ = read_disagreements(workspace)
        assert metrics["agreement_type"] == agreement.INTER
        assert config["agreement_type"] == agreement.INTER
        assert header["agreement_type"] == agreement.INTER
        assert "INTER-ANNOTATOR" in output
        assert "INTRA" not in output

    def test_passes_means_intra_annotator_everywhere(self, workspace):
        code, output = run(workspace, spread(self.LABELS), flag="--passes")
        assert code == 0
        metrics, config, _ = read_outputs(workspace)
        header, _ = read_disagreements(workspace)
        assert metrics["agreement_type"] == agreement.INTRA
        assert config["agreement_type"] == agreement.INTRA
        assert header["agreement_type"] == agreement.INTRA
        assert "INTRA-ANNOTATOR" in output

    def test_intra_states_the_conditions_it_cannot_verify(self, workspace):
        _, output = run(workspace, spread(self.LABELS), flag="--passes")
        metrics, _, _ = read_outputs(workspace)
        assert "blind" in output and "week" in output
        assert any("blind" in note for note in metrics["notes"])

    def test_inter_does_not_carry_the_intra_caveat(self, workspace):
        _, output = run(workspace, spread(self.LABELS), flag="--sheets")
        assert "blind" not in output

    def test_both_flags_at_once_is_refused(self, workspace):
        paths = write_sheets(workspace["sheets"], spread(self.LABELS))
        with pytest.raises(SystemExit):
            agreement.main(["--sheets", str(paths[0]), str(paths[1]),
                            "--passes", str(paths[0]), str(paths[1])], out=io.StringIO())

    def test_neither_flag_is_refused(self):
        with pytest.raises(SystemExit):
            agreement.main([], out=io.StringIO())


# ------------------------------------------------------------------ the three specified cases


class TestPerfectAgreement:
    def test_kappa_is_one_and_the_abstention_types_meet_the_threshold(self, workspace):
        items = spread(("NO-OP", "ABSTAIN:insufficient", "ABSTAIN:ambiguous",
                        "ABSTAIN:conflicting"), conversations=6, per_conversation=8)
        code, output = run(workspace, items)
        assert code == 0
        metrics, _, _ = read_outputs(workspace)
        assert metrics["overall"]["kappa"] == 1.0
        assert metrics["overall"]["percent_agreement"] == 1.0
        for label in thresholds.ABSTENTION_TYPES:
            row = metrics["verdict"]["per_abstention_type"][label]
            assert row["verdict"] == "MEETS", (label, row)
        assert metrics["verdict"]["hypothesis"] == "not refuted by the pre-registered rule"
        assert "NOT REFUTED" in output.upper()


class TestChanceLevelAgreement:
    def test_kappa_is_zero_and_the_abstention_types_fall_below(self, workspace):
        """A 2x2 chance table per label, replicated across conversations.

        One of each cell gives po = pe = 0.5 exactly, so kappa is 0 on the nose rather than
        approximately zero.
        """
        items = []
        for c in range(1, 9):
            for turn, (a, b) in enumerate([
                ("ABSTAIN:insufficient", "ABSTAIN:insufficient"),
                ("ABSTAIN:insufficient", "NO-OP"),
                ("NO-OP", "ABSTAIN:insufficient"),
                ("NO-OP", "NO-OP"),
            ]):
                items.append(item(f"conv_{c:03d}", turn, "budget", a, b))
        code, _ = run(workspace, items)
        assert code == 0
        metrics, _, _ = read_outputs(workspace)
        assert metrics["overall"]["kappa"] == 0.0
        insufficient = metrics["per_category"]["ABSTAIN:insufficient"]
        assert insufficient["kappa"] == 0.0
        assert insufficient["interpretable"] is True
        assert metrics["verdict"]["per_abstention_type"]["ABSTAIN:insufficient"]["verdict"] \
            == "BELOW"


class TestRareCategory:
    """A category under ten items is reported with its counts and marked, never dropped."""

    def build(self, workspace):
        items = spread(("NO-OP", "ABSTAIN:insufficient", "ABSTAIN:ambiguous"),
                       conversations=6, per_conversation=7)
        # three items of a fourth category, agreed on perfectly: a tempting kappa of 1.0
        items += [item("conv_007", t, "budget", "ABSTAIN:conflicting") for t in range(3)]
        return run(workspace, items)

    def test_it_is_present_with_its_counts_not_dropped(self, workspace):
        self.build(workspace)
        metrics, _, _ = read_outputs(workspace)
        rare = metrics["per_category"]["ABSTAIN:conflicting"]
        assert rare["n_either"] == 3
        assert rare["n_rater_a"] == 3 and rare["n_rater_b"] == 3 and rare["n_both"] == 3
        assert rare["kappa"] == 1.0

    def test_but_it_is_marked_not_interpretable_with_the_reason(self, workspace):
        self.build(workspace)
        metrics, _, _ = read_outputs(workspace)
        rare = metrics["per_category"]["ABSTAIN:conflicting"]
        assert rare["interpretable"] is False
        assert f"< {thresholds.MIN_CATEGORY_N}" in rare["reason"]

    def test_a_perfect_kappa_on_three_items_does_not_pass_the_hypothesis(self, workspace):
        _, output = self.build(workspace)
        metrics, _, _ = read_outputs(workspace)
        assert metrics["verdict"]["per_abstention_type"]["ABSTAIN:conflicting"]["verdict"] \
            == "NOT INTERPRETABLE"
        assert metrics["verdict"]["hypothesis"] == "cannot be evaluated"
        assert "CANNOT BE EVALUATED" in output
        assert "not interpretable" in output

    def test_the_floor_is_the_pre_registered_one(self, workspace):
        assert thresholds.MIN_CATEGORY_N == 10


# ------------------------------------------------------------------ what goes where


class TestNothingSensitiveReachesRuns:
    LABELS = ("NO-OP", "VALUE", "ABSTAIN:insufficient", "ABSTAIN:ambiguous")

    def test_no_sheet_text_and_no_item_id_in_either_run_file(self, workspace):
        items = spread(self.LABELS, conversations=4, per_conversation=5)
        items[0]["label_b"] = "HEDGED"
        items[1] = item("conv_001", 1, "budget", "VALUE", "VALUE", "40-45 lakhs", "40 to 45 lakhs")
        run(workspace, items)
        _, _, run_dir = read_outputs(workspace)
        for name in ("metrics.json", "config.json"):
            body = (run_dir / name).read_text(encoding="utf-8")
            assert CANARY not in body, name
            assert "conv_001#" not in body, name
            assert "lakhs" not in body, name

    def test_only_the_two_expected_files_are_written_under_runs(self, workspace):
        run(workspace, spread(self.LABELS))
        _, _, run_dir = read_outputs(workspace)
        assert sorted(p.name for p in run_dir.iterdir()) == ["config.json", "metrics.json"]

    def test_the_experiment_record_is_not_touched(self, workspace):
        """Result, Interpretation and Decision stay a human's to write."""
        record = safety.repo_root() / "docs/research/experiments/EXP-000-label-feasibility.md"
        before = hashlib.sha256(record.read_bytes()).hexdigest()
        run(workspace, spread(self.LABELS))
        assert hashlib.sha256(record.read_bytes()).hexdigest() == before

    def test_the_metrics_say_the_verdict_is_not_a_result(self, workspace):
        run(workspace, spread(self.LABELS))
        metrics, _, _ = read_outputs(workspace)
        note = metrics["verdict"]["note"]
        assert "not a Result" in note
        assert "human" in note

    def test_a_disagreements_dir_outside_data_scrubbed_is_refused(self, workspace, tmp_path):
        paths = write_sheets(workspace["sheets"], spread(self.LABELS))
        with pytest.raises(safety.OutsideOutputRoot, match="data/scrubbed"):
            agreement.main(
                ["--sheets", str(paths[0]), str(paths[1]),
                 "--out-root", str(workspace["runs"]),
                 "--disagreements-dir", str(tmp_path / "elsewhere"), "--bootstrap", "10"],
                runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"],
                out=io.StringIO())

    def test_a_run_dir_outside_runs_is_refused(self, workspace, tmp_path):
        paths = write_sheets(workspace["sheets"], spread(self.LABELS))
        with pytest.raises(safety.OutsideOutputRoot, match="runs/EXP-000"):
            agreement.main(
                ["--sheets", str(paths[0]), str(paths[1]),
                 "--out-root", str(tmp_path / "elsewhere"),
                 "--disagreements-dir", str(workspace["scrubbed"]), "--bootstrap", "10"],
                runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"],
                out=io.StringIO())


class TestDisagreementList:
    def test_a_label_disagreement_carries_both_labels_and_no_values(self, workspace):
        items = spread(("NO-OP",), conversations=4, per_conversation=4)
        items[0]["label_b"] = "ABSTAIN:ambiguous"
        run(workspace, items)
        _, rows = read_disagreements(workspace)
        labels = [r for r in rows if r["kind"] == "label"]
        assert len(labels) == 1
        assert labels[0]["label_a"] == "NO-OP" and labels[0]["label_b"] == "ABSTAIN:ambiguous"
        assert "value_a" not in labels[0]

    def test_a_value_mismatch_carries_both_values(self, workspace):
        items = spread(("NO-OP",), conversations=4, per_conversation=4)
        items[0] = item("conv_001", 0, "budget", "VALUE", "VALUE",
                        "40-45 lakhs", "40 to 45 lakhs")
        run(workspace, items)
        _, rows = read_disagreements(workspace)
        mismatches = [r for r in rows if r["kind"] == "value"]
        assert len(mismatches) == 1
        assert mismatches[0]["value_a"] == "40-45 lakhs"
        assert mismatches[0]["value_b"] == "40 to 45 lakhs"
        assert mismatches[0]["agrees_under_number_aware"] is True

    def test_agreeing_items_are_absent(self, workspace):
        run(workspace, spread(("NO-OP",), conversations=4, per_conversation=4))
        header, rows = read_disagreements(workspace)
        assert rows == []
        assert header["disagreements"] == 0

    def test_the_header_warns_what_the_file_holds(self, workspace):
        run(workspace, spread(("NO-OP", "VALUE")))
        header, _ = read_disagreements(workspace)
        assert "gitignored" in header["_warning"]


# ------------------------------------------------------------------ value agreement


class TestValueAgreement:
    def build(self):
        items = []
        for c in range(1, 5):
            for turn, (a, b) in enumerate([
                ("40-45 lakhs", "40 to 45 lakhs"),   # differs strictly, same number-aware
                ("50 lakhs", "50 lakhs"),            # same under both
                ("60 lakhs", "70 lakhs"),            # differs under both
            ]):
                items.append(item(f"conv_{c:03d}", turn, "budget", "VALUE", "VALUE", a, b))
        return items

    def test_it_covers_only_items_both_sheets_called_value(self, workspace):
        items = self.build()
        items.append(item("conv_009", 0, "budget", "VALUE", "NO-OP", "80 lakhs", ""))
        items.append(item("conv_009", 1, "budget", "NO-OP", "NO-OP"))
        run(workspace, items)
        metrics, _, _ = read_outputs(workspace)
        assert metrics["value_agreement"]["n_both_value"] == 12

    def test_strict_is_the_primary_and_the_looser_figure_is_separate(self, workspace):
        run(workspace, self.build())
        metrics, _, _ = read_outputs(workspace)
        value = metrics["value_agreement"]
        assert value["primary_normalization"] == "strict"
        # 4 of 12 agree strictly, 8 of 12 once numbers are resolved.
        assert value["strict"]["agreement"] == pytest.approx(4 / 12)
        assert value["number_aware"]["agreement"] == pytest.approx(8 / 12)
        assert value["number_aware"]["agreement"] > value["strict"]["agreement"]

    def test_label_agreement_can_be_perfect_while_values_disagree(self, workspace):
        """The reason value agreement is reported separately at all."""
        run(workspace, self.build())
        metrics, _, _ = read_outputs(workspace)
        assert metrics["overall"]["kappa"] is None  # one label everywhere: undefined, not 1.0
        assert metrics["overall"]["percent_agreement"] == 1.0
        assert metrics["value_agreement"]["strict"]["agreement"] < 1.0

    def test_no_value_items_leaves_the_figure_empty_not_zero(self, workspace):
        run(workspace, spread(("NO-OP", "ABSTAIN:ambiguous")))
        metrics, _, _ = read_outputs(workspace)
        assert metrics["value_agreement"]["n_both_value"] == 0
        assert metrics["value_agreement"]["strict"]["agreement"] is None


# ------------------------------------------------------------------ inputs it refuses


class TestInputValidation:
    LABELS = ("NO-OP", "VALUE", "ABSTAIN:insufficient")

    def test_a_label_outside_the_vocabulary_is_an_error_naming_it(self, workspace):
        items = spread(self.LABELS)
        items[0]["label_b"] = "ABSTAIN:insuficient"  # one letter short
        with pytest.raises(agreement.AgreementError) as caught:
            run(workspace, items)
        message = str(caught.value)
        assert "ABSTAIN:insuficient" in message
        assert "conv_001#0#budget" in message

    def test_a_blank_label_is_excluded_and_counted(self, workspace):
        items = spread(self.LABELS, conversations=4, per_conversation=5)
        items[0]["label_b"] = ""
        items[1]["label_a"] = ""
        code, output = run(workspace, items)
        assert code == 0
        metrics, config, _ = read_outputs(workspace)
        assert metrics["items_excluded_unlabelled"] == 2
        assert metrics["n_items_compared"] == len(items) - 2
        assert "unlabelled" in output

    def test_all_blank_is_an_error_rather_than_an_empty_report(self, workspace):
        items = spread(self.LABELS, conversations=2, per_conversation=2)
        for entry in items:
            entry["label_b"] = ""
        with pytest.raises(agreement.AgreementError, match="empty label"):
            run(workspace, items)

    def test_a_duplicate_item_id_is_an_error(self, workspace):
        items = spread(self.LABELS, conversations=2, per_conversation=2)
        items.append(items[0].copy())
        with pytest.raises(agreement.AgreementError, match="appears twice"):
            run(workspace, items)

    def test_a_missing_required_column_is_an_error_naming_it(self, workspace):
        columns = tuple(c for c in SHEET_COLUMNS if c != "value")
        with pytest.raises(agreement.AgreementError, match="value"):
            run(workspace, spread(self.LABELS), columns=columns)

    def test_a_missing_conversation_id_is_an_error_that_explains_why(self, workspace):
        items = spread(self.LABELS, conversations=2, per_conversation=2)
        paths = write_sheets(workspace["sheets"], items)
        # Blank the conversation_id column only. Replacing the bare id would hit the item_id
        # first and produce a different error.
        body = paths[0].read_text(encoding="utf-8").replace(",conv_001,", ",,", 1)
        paths[0].write_text(body, encoding="utf-8")
        with pytest.raises(agreement.AgreementError, match="bootstrap"):
            run(workspace, paths=paths, write=False)

    def test_differing_item_sets_are_an_error_by_default(self, workspace):
        items = spread(self.LABELS, conversations=3, per_conversation=4)
        paths = write_sheets(workspace["sheets"], items)
        rows = paths[1].read_text(encoding="utf-8").splitlines()
        paths[1].write_text("\n".join(rows[:-2]) + "\n", encoding="utf-8")
        with pytest.raises(agreement.AgreementError, match="allow-partial-overlap"):
            run(workspace, paths=paths, write=False)

    def test_allow_partial_overlap_measures_the_shared_items_and_records_it(self, workspace):
        items = spread(self.LABELS, conversations=4, per_conversation=5)
        paths = write_sheets(workspace["sheets"], items)
        rows = paths[1].read_text(encoding="utf-8").splitlines()
        paths[1].write_text("\n".join(rows[:-2]) + "\n", encoding="utf-8")
        code, output = run(workspace, paths=paths, write=False,
                           extra=("--allow-partial-overlap",))
        assert code == 0
        metrics, config, _ = read_outputs(workspace)
        assert metrics["n_items_compared"] == len(items) - 2
        assert metrics["items_only_in_sheet_a"] == 2
        assert config["alignment"]["partial_overlap_allowed"] is True
        assert "not shared" in output

    def test_sheets_describing_different_samples_are_an_error(self, workspace):
        items = spread(self.LABELS, conversations=2, per_conversation=3)
        paths = write_sheets(workspace["sheets"], items)
        body = paths[1].read_text(encoding="utf-8")
        # same item_ids, different conversation_id column
        body = body.replace(",conv_001,", ",conv_999,")
        paths[1].write_text(body, encoding="utf-8")
        with pytest.raises(agreement.AgreementError, match="not two views of the same sample"):
            run(workspace, paths=paths, write=False)

    def test_an_empty_sheet_is_an_error(self, workspace):
        workspace["sheets"].mkdir(parents=True, exist_ok=True)
        empty = workspace["sheets"] / "empty.csv"
        empty.write_text(",".join(SHEET_COLUMNS) + "\n", encoding="utf-8")
        with pytest.raises(agreement.AgreementError, match="no rows"):
            run(workspace, paths=(empty, empty), write=False)

    def test_a_missing_file_is_an_error(self, workspace, tmp_path):
        missing = tmp_path / "nope.csv"
        with pytest.raises(agreement.AgreementError, match="not a file"):
            run(workspace, paths=(missing, missing), write=False)


# ------------------------------------------------------------------ recorded settings


class TestRecordedSettings:
    LABELS = ("NO-OP", "VALUE", "ABSTAIN:insufficient", "ABSTAIN:ambiguous")

    def test_the_primary_interval_is_the_conversation_cluster_one(self, workspace):
        run(workspace, spread(self.LABELS))
        metrics, config, _ = read_outputs(workspace)
        assert config["bootstrap"]["primary_unit"] == "conversation"
        assert metrics["overall"]["primary_unit"] == "conversation"
        assert "ci_conversation" in metrics["overall"]
        assert "ci_item" in metrics["overall"]

    def test_the_pre_registered_numbers_are_recorded_with_the_run(self, workspace):
        run(workspace, spread(self.LABELS))
        _, config, _ = read_outputs(workspace)
        recorded = config["thresholds"]
        assert recorded["kappa_threshold"] == thresholds.KAPPA_THRESHOLD
        assert recorded["min_category_n"] == thresholds.MIN_CATEGORY_N
        assert recorded["kappa_tolerance"] == thresholds.KAPPA_TOLERANCE
        assert recorded["hedged_rule"] == thresholds.HEDGED_RULE
        assert recorded["abstention_types"] == list(thresholds.ABSTENTION_TYPES)

    def test_the_run_records_its_commit_and_seed(self, workspace):
        run(workspace, spread(self.LABELS), extra=("--seed", "7"))
        _, config, _ = read_outputs(workspace)
        assert config["seed"] == 7
        assert config["git_commit"]
        assert config["inputs"]["sheet_a"]["sha256"]

    def test_the_verdict_applies_only_to_the_abstention_types(self, workspace):
        run(workspace, spread(self.LABELS))
        metrics, _, _ = read_outputs(workspace)
        assert list(metrics["verdict"]["per_abstention_type"]) == \
            list(thresholds.ABSTENTION_TYPES)
        assert "HEDGED" not in metrics["verdict"]["per_abstention_type"]
        # but HEDGED still gets a kappa reported
        assert "HEDGED" in metrics["per_category"]
        assert metrics["per_category"]["HEDGED"]["is_abstention_type"] is False

    def test_every_vocabulary_label_gets_a_row_even_if_unused(self, workspace):
        run(workspace, spread(("NO-OP", "VALUE")))
        metrics, _, _ = read_outputs(workspace)
        assert list(metrics["per_category"]) == list(thresholds.LABELS)
        unused = metrics["per_category"]["ABSTAIN:conflicting"]
        assert unused["n_either"] == 0 and unused["kappa"] is None
        assert unused["interpretable"] is False

    def test_the_confusion_matrix_margins_match_the_label_counts(self, workspace):
        items = spread(self.LABELS, conversations=4, per_conversation=5)
        items[0]["label_b"] = "HEDGED"
        run(workspace, items)
        metrics, _, _ = read_outputs(workspace)
        matrix = metrics["confusion_matrix"]
        labels, counts = matrix["labels"], matrix["counts"]
        assert sum(sum(row) for row in counts) == metrics["n_items_compared"]
        for label, row in zip(labels, counts):
            assert sum(row) == metrics["label_use"]["sheet_a"].get(label, 0)
        for label, column in zip(labels, zip(*counts)):
            assert sum(column) == metrics["label_use"]["sheet_b"].get(label, 0)

    def test_the_same_seed_reproduces_the_whole_report(self, workspace, tmp_path):
        items = spread(self.LABELS, conversations=5, per_conversation=4)
        first, _ = run(workspace, items, extra=("--run-id", "fixed"))
        metrics_one, _, _ = read_outputs(workspace)
        second = {"sheets": tmp_path / "s2", "runs": tmp_path / "r2",
                  "scrubbed": tmp_path / "d2"}
        run(second, items, extra=("--run-id", "fixed"))
        metrics_two, _, _ = read_outputs(second)
        assert metrics_one["overall"] == metrics_two["overall"]
        assert metrics_one["per_category"] == metrics_two["per_category"]


# ------------------------------------------------------------------ the local-tool guarantees


class TestLocalToolGuarantees:
    LABELS = ("NO-OP", "VALUE", "ABSTAIN:insufficient")

    def test_makes_no_network_call(self, workspace, monkeypatch):
        def boom(*args, **kwargs):
            raise AssertionError("agreement.py must not open a network connection")

        import socket
        monkeypatch.setattr(socket, "socket", boom)
        monkeypatch.setattr(socket, "create_connection", boom)
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        code, _ = run(workspace, spread(self.LABELS))
        assert code == 0

    def test_never_modifies_the_sheets(self, workspace):
        paths = write_sheets(workspace["sheets"], spread(self.LABELS))
        before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        run(workspace, paths=paths, write=False)
        after = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
        assert after == before and before


class TestShuffledSheetsChangeNothing:
    """The sampler gives each annotator their own item order. No number may depend on it.

    agreement.py joins on item_id and `align` sorts the shared ids, so the comparison order is
    canonical whatever order the sheets arrive in. These tests hold that property down, because
    if it ever broke, the two annotators' different orders would silently change the kappa.
    """

    #: No VALUE here: the two VALUE/VALUE items are set explicitly below, so n_both_value is
    #: exactly 2 and the value-agreement arithmetic is checkable by hand.
    LABELS = ("NO-OP", "ABSTAIN:insufficient", "ABSTAIN:ambiguous", "HEDGED")

    def items(self):
        entries = spread(self.LABELS, conversations=5, per_conversation=6)
        entries[0]["label_b"] = "HEDGED"          # one label disagreement
        # Mutated in place rather than replaced, so no item_id is duplicated.
        entries[3].update(label_a="VALUE", label_b="VALUE",
                          value_a="~40 lakhs", value_b="around 40 lakhs")
        entries[4].update(label_a="VALUE", label_b="VALUE",
                          value_a="~40 lakhs", value_b="40 lakhs")
        return entries

    def shuffle_sheet(self, path, seed):
        rows = read_sheet(path)
        random.Random(seed).shuffle(rows)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(SHEET_COLUMNS))
            writer.writeheader()
            writer.writerows(rows)

    def test_every_number_is_identical_whatever_order_the_sheets_use(self, workspace, tmp_path):
        entries = self.items()
        run(workspace, entries, extra=("--run-id", "fixed"))
        ordered, _, _ = read_outputs(workspace)

        shuffled = {"sheets": tmp_path / "s", "runs": tmp_path / "r",
                    "scrubbed": tmp_path / "d"}
        paths = write_sheets(shuffled["sheets"], entries)
        self.shuffle_sheet(paths[0], 1)
        self.shuffle_sheet(paths[1], 2)
        run(shuffled, paths=paths, write=False, extra=("--run-id", "fixed"))
        reordered, _, _ = read_outputs(shuffled)

        assert reordered["overall"] == ordered["overall"]
        assert reordered["per_category"] == ordered["per_category"]
        assert reordered["confusion_matrix"] == ordered["confusion_matrix"]
        assert reordered["value_agreement"] == ordered["value_agreement"]
        assert reordered["verdict"] == ordered["verdict"]

    def test_the_two_sheets_really_were_in_different_orders(self, workspace, tmp_path):
        """Guards the test above from passing because the shuffle did nothing."""
        paths = write_sheets(tmp_path / "s", self.items())
        before = [row["item_id"] for row in read_sheet(paths[0])]
        self.shuffle_sheet(paths[0], 1)
        self.shuffle_sheet(paths[1], 2)
        after_a = [row["item_id"] for row in read_sheet(paths[0])]
        after_b = [row["item_id"] for row in read_sheet(paths[1])]
        assert after_a != before
        assert after_a != after_b
        assert set(after_a) == set(after_b)

    def test_an_approximation_counts_as_a_value_disagreement(self, workspace):
        """Kapardhi's Q1 decision puts approximations in VALUE, so "~40 lakhs" vs "40 lakhs"
        is a real disagreement about the value and must not be normalized away."""
        run(workspace, self.items())
        metrics, _, _ = read_outputs(workspace)
        value = metrics["value_agreement"]
        assert value["n_both_value"] == 2
        # "~40 lakhs" vs "around 40 lakhs" agree only under number_aware;
        # "~40 lakhs" vs "40 lakhs" agree under neither.
        assert value["strict"]["agreement"] == pytest.approx(0.0)
        assert value["number_aware"]["agreement"] == pytest.approx(0.5)


class TestPerSourceReporting:
    """--manifest splits the result. Only the real subset's verdict bears on ADR-003."""

    LABELS = ("NO-OP", "VALUE", "ABSTAIN:insufficient", "ABSTAIN:ambiguous",
              "ABSTAIN:conflicting", "HEDGED")

    def build(self, workspace, *, real_agree=0.55, synthetic_agree=1.0):
        """Items from two sources, with the synthetic ones agreeing more often."""
        entries, rng = [], random.Random(3)
        sources = {}
        for source, conversations in (("real", range(1, 5)), ("synthetic", range(5, 9))):
            for c in conversations:
                for turn in range(5):
                    for field in ("budget", "location_preference"):
                        label = self.LABELS[(c + turn) % len(self.LABELS)]
                        rate = real_agree if source == "real" else synthetic_agree
                        other = label if rng.random() < rate else rng.choice(self.LABELS)
                        entry = item(f"c{c:03d}", turn, field, label, other)
                        entries.append(entry)
                        sources[f"c{c:03d}#{turn}#{field}"] = source
        manifest = workspace["sheets"] / "manifest.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({"item_source": sources}), encoding="utf-8")
        return entries, manifest

    def test_it_reports_three_blocks(self, workspace):
        entries, manifest = self.build(workspace)
        code, output = run(workspace, entries, extra=("--manifest", str(manifest)))
        assert code == 0
        metrics, _, _ = read_outputs(workspace)
        assert set(metrics["by_source"]) == {"real", "synthetic"}
        assert metrics["overall"]["kappa"] is not None       # the combined figure is still there
        assert "BY SOURCE" in output

    def test_only_the_real_subset_bears_on_adr_003(self, workspace):
        entries, manifest = self.build(workspace)
        _, output = run(workspace, entries, extra=("--manifest", str(manifest)))
        metrics, _, _ = read_outputs(workspace)
        assert metrics["by_source"]["real"]["verdict"]["bears_on_adr_003"] is True
        assert metrics["by_source"]["synthetic"]["verdict"]["bears_on_adr_003"] is False
        assert metrics["adr_003_subset"] == "real"

    def test_the_synthetic_verdict_carries_its_label(self, workspace):
        entries, manifest = self.build(workspace)
        _, output = run(workspace, entries, extra=("--manifest", str(manifest)))
        metrics, _, _ = read_outputs(workspace)
        note = metrics["by_source"]["synthetic"]["verdict"]["reads_as"]
        assert note == "guideline usability, not evidence for ADR-003"
        assert note in output
        assert "not evidence for ADR-003" in output

    def test_the_combined_figure_can_disagree_with_the_real_one(self, workspace):
        """The whole reason for the split.

        Synthetic items that agree far more often pull the combined kappa up, so a single
        number over a mixed item set can read NOT REFUTED while the real subset is REFUTED.
        """
        entries, manifest = self.build(workspace, real_agree=0.45, synthetic_agree=1.0)
        run(workspace, entries, extra=("--manifest", str(manifest)))
        metrics, _, _ = read_outputs(workspace)
        real = metrics["by_source"]["real"]["overall"]["kappa"]
        combined = metrics["overall"]["kappa"]
        assert combined > real, (combined, real)

    def test_each_subset_gets_its_own_counts(self, workspace):
        entries, manifest = self.build(workspace)
        run(workspace, entries, extra=("--manifest", str(manifest)))
        metrics, _, _ = read_outputs(workspace)
        blocks = metrics["by_source"]
        assert blocks["real"]["n_items_compared"] + blocks["synthetic"]["n_items_compared"] \
            == metrics["n_items_compared"]
        assert blocks["real"]["n_conversations"] == 4

    def test_without_the_flag_nothing_changes(self, workspace):
        entries, _ = self.build(workspace)
        code, output = run(workspace, entries)
        assert code == 0
        metrics, _, _ = read_outputs(workspace)
        assert "by_source" not in metrics
        assert "BY SOURCE" not in output

    def test_a_manifest_from_another_run_is_a_loud_error(self, workspace):
        entries, manifest = self.build(workspace)
        stale = json.loads(manifest.read_text(encoding="utf-8"))
        stale["item_source"].pop(next(iter(stale["item_source"])))
        manifest.write_text(json.dumps(stale), encoding="utf-8")
        with pytest.raises(agreement.AgreementError, match="different sampler runs"):
            run(workspace, entries, extra=("--manifest", str(manifest)))

    def test_a_manifest_without_the_map_is_a_loud_error(self, workspace, tmp_path):
        entries, _ = self.build(workspace)
        empty = tmp_path / "old_manifest.json"
        empty.write_text(json.dumps({"tool": "EXP-000 sample_items.py"}), encoding="utf-8")
        with pytest.raises(agreement.AgreementError, match="no 'item_source' map"):
            run(workspace, entries, extra=("--manifest", str(empty)))

    def test_no_source_or_text_reaches_runs(self, workspace):
        entries, manifest = self.build(workspace)
        run(workspace, entries, extra=("--manifest", str(manifest)))
        _, _, run_dir = read_outputs(workspace)
        for name in ("metrics.json", "config.json"):
            body = (run_dir / name).read_text(encoding="utf-8")
            assert CANARY not in body
            assert "c001#" not in body


class TestTheDisagreementsDirDefault:
    """The default is the directory holding the first sheet. Kapardhi's decision, 2026-10-05.

    It used to be `data/scrubbed/EXP-000`. After the corpus was renamed to `EXP-000-v2` that
    named nothing which existed, and because `write_disagreements` calls `mkdir(parents=True)`
    the first run would have created a third directory there holding one file, beside the
    corpus and the sheets. Defaulting beside sheet A creates nothing, since the sheet was read
    from that directory a moment earlier.
    """

    LABELS = ("NO-OP", "VALUE", "ABSTAIN:ambiguous", "ABSTAIN:insufficient")

    @staticmethod
    def sheets_inside_scrubbed(workspace, items):
        """Sheets under the scrubbed root, which is where the real ones live."""
        return write_sheets(workspace["scrubbed"] / "EXP-000-v3-annotation", items)

    def test_the_default_lands_beside_sheet_a(self, workspace):
        paths = self.sheets_inside_scrubbed(workspace, spread(self.LABELS))
        buffer = io.StringIO()
        code = agreement.main(
            ["--sheets", str(paths[0]), str(paths[1]),
             "--out-root", str(workspace["runs"]), "--bootstrap", "10"],
            runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"], out=buffer)
        assert code == 0
        written = sorted(paths[0].parent.glob("disagreements_*.jsonl"))
        assert len(written) == 1, sorted(paths[0].parent.iterdir())
        assert written[0].parent == paths[0].parent

    def test_the_default_creates_no_new_directory(self, workspace):
        """The whole point: nothing appears under data/scrubbed/ that was not there before."""
        paths = self.sheets_inside_scrubbed(workspace, spread(self.LABELS))
        before = {p.name for p in workspace["scrubbed"].iterdir()}
        agreement.main(
            ["--sheets", str(paths[0]), str(paths[1]),
             "--out-root", str(workspace["runs"]), "--bootstrap", "10"],
            runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"],
            out=io.StringIO())
        assert {p.name for p in workspace["scrubbed"].iterdir()} == before
        assert not (workspace["scrubbed"] / "EXP-000").exists(), "the old default's directory"

    def test_an_explicit_dir_still_wins(self, workspace):
        paths = self.sheets_inside_scrubbed(workspace, spread(self.LABELS))
        elsewhere = workspace["scrubbed"] / "somewhere-else"
        agreement.main(
            ["--sheets", str(paths[0]), str(paths[1]),
             "--out-root", str(workspace["runs"]),
             "--disagreements-dir", str(elsewhere), "--bootstrap", "10"],
            runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"],
            out=io.StringIO())
        assert sorted(elsewhere.glob("disagreements_*.jsonl"))
        assert not sorted(paths[0].parent.glob("disagreements_*.jsonl"))

    def test_a_sheet_outside_data_scrubbed_is_still_refused(self, workspace, tmp_path):
        """Containment is not weakened by the new default: it is the same check, later."""
        outside = write_sheets(tmp_path / "not-scrubbed", spread(self.LABELS))
        with pytest.raises(safety.OutsideOutputRoot, match="data/scrubbed"):
            agreement.main(
                ["--sheets", str(outside[0]), str(outside[1]),
                 "--out-root", str(workspace["runs"]), "--bootstrap", "10"],
                runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"],
                out=io.StringIO())

    def test_intra_annotator_passes_default_beside_the_first_pass(self, workspace):
        """`--passes` resolves the same way; the first path is the first path either way."""
        paths = self.sheets_inside_scrubbed(workspace, spread(self.LABELS))
        agreement.main(
            ["--passes", str(paths[0]), str(paths[1]),
             "--out-root", str(workspace["runs"]), "--bootstrap", "10"],
            runs_root=workspace["runs"], scrubbed_root=workspace["scrubbed"],
            out=io.StringIO())
        assert sorted(paths[0].parent.glob("disagreements_*.jsonl"))
