"""Stage 1: the baselines, the split writer, and the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import HEADER, SENTINEL, item

from baselines import (
    fit_majority,
    fit_predict_lexical,
    parse_failures,
    predict_majority,
    to_scored,
    vocabulary_of,
)
from data import Item, apply_split, labelled, load_split_assignment, of_split
from make_split import assign
from make_split import main as split_main
from run_stage1 import main as stage1_main
from safety import OutputSafetyError, assert_output_safe
from thresholds import DEV_ITEMS_TARGET, TEST_ITEMS_TARGET


# --- B-triv-maj -----------------------------------------------------------------------------------

def test_majority_picks_the_most_frequent_action():
    train = [item(2, "c", "m", "a")] * 3 + [item(3, "c", "m", "b")]
    assert fit_majority(train) == "a"


def test_majority_breaks_ties_deterministically():
    train = [item(2, "c", "m", "b"), item(3, "c", "m", "a")]
    assert fit_majority(train) == fit_majority(list(reversed(train)))


def test_majority_normalises_case_and_whitespace():
    train = [item(2, "c", "m", " Ask_Budget "), item(3, "c", "m", "ask_budget")]
    assert fit_majority(train) == "ask_budget"


def test_majority_refuses_an_unlabelled_train_split():
    with pytest.raises(ValueError, match="no labelled training items"):
        fit_majority([item(2, "c", "m", "")])


def test_majority_predictions_skip_unlabelled_items():
    preds = predict_majority("a", [item(2, "c", "m", "a"), item(3, "c", "m", "")])
    assert len(preds) == 1


def test_predictions_score_by_exact_match_after_normalisation():
    preds = predict_majority("ask_budget", [item(2, "c", "m", "ASK_BUDGET")])
    assert preds[0].correct is True
    preds = predict_majority("ask_budget", [item(2, "c", "m", "ask budget")])
    assert preds[0].correct is False, "only case and whitespace are normalised, not separators"


# --- B-triv-lex -----------------------------------------------------------------------------------

def test_lexical_baseline_finds_a_blatant_signal(lexical_items):
    """If it cannot separate two disjoint vocabularies, it is broken rather than the task hard."""
    pytest.importorskip("sklearn")
    train, evaluate = lexical_items[:48], lexical_items[48:]
    preds, settings = fit_predict_lexical(train, evaluate, seed=0)
    acc = sum(1 for p in preds if p.correct) / len(preds)
    assert acc > 0.9
    assert settings["n_classes_in_train"] == 2


def test_lexical_baseline_is_deterministic_under_a_seed(lexical_items):
    pytest.importorskip("sklearn")
    a, _ = fit_predict_lexical(lexical_items[:48], lexical_items[48:], seed=0)
    b, _ = fit_predict_lexical(lexical_items[:48], lexical_items[48:], seed=0)
    assert [p.predicted for p in a] == [p.predicted for p in b]


def test_lexical_baseline_refuses_a_single_class_train_split():
    """It would then be the majority baseline under another name, not a second baseline."""
    pytest.importorskip("sklearn")
    train = [item(2 + n, "c", f"m{n}", "a") for n in range(5)]
    with pytest.raises(ValueError, match="single `action` class"):
        fit_predict_lexical(train, train, seed=0)


def test_lexical_settings_are_recorded_not_tuned(lexical_items):
    """Tuning a baseline on dev would overstate the floor Gate 2 compares against."""
    pytest.importorskip("sklearn")
    _, settings = fit_predict_lexical(lexical_items[:48], lexical_items[48:], seed=0)
    assert settings["ngram_range"] == [1, 2]
    assert settings["sublinear_tf"] is True
    assert settings["random_state"] == 0


# --- parse failures -------------------------------------------------------------------------------

def test_stage_one_baselines_cannot_produce_a_parse_failure():
    vocab = vocabulary_of([item(2, "c", "m", "a")])
    preds = predict_majority("a", [item(3, "c", "m", "a")])
    assert parse_failures(preds, vocab) == 0


def test_parse_failures_counts_out_of_vocabulary_predictions():
    vocab = {"a", "b"}
    preds = predict_majority("not_a_class", [item(2, "c", "m", "a")])
    assert parse_failures(preds, vocab) == 1


# --- the split writer -----------------------------------------------------------------------------

def _corpus(n_conv: int, per_conv: int) -> list[Item]:
    out: list[Item] = []
    row = 2
    for c in range(n_conv):
        for t in range(per_conv):
            out.append(item(row, f"conv-{c:03d}", f"m{row}", "a", turn=t + 1))
            row += 1
    return out


def test_split_never_puts_one_conversation_in_two_splits():
    """A conversation straddling a boundary is how a duplicate message leaks across it."""
    items = _corpus(140, 3)
    assignment, _ = assign(items, pilot_conversations=set(), seed=0)
    by_conv: dict[str, set[str]] = {}
    for it in items:
        by_conv.setdefault(it.conversation_id, set()).add(assignment[it.item_id])
    assert all(len(v) == 1 for v in by_conv.values())


def test_split_assigns_every_item():
    items = _corpus(140, 3)
    assignment, report = assign(items, pilot_conversations=set(), seed=0)
    assert len(assignment) == len(items)
    assert sum(report["counts"].values()) == len(items)


def test_split_refuses_a_corpus_too_small_for_the_targets():
    """It would otherwise drain every conversation into test and freeze a useless split."""
    with pytest.raises(ValueError, match="needs more than"):
        assign(_corpus(24, 3), pilot_conversations=set(), seed=0)


def test_split_refuses_when_conversations_are_too_few_and_large():
    """450 items is plenty, but three conversations of 150 cannot fill three splits: test takes
    two to clear 200, dev takes the third, and train is left empty. A conversation is never
    divided across splits, so the item count alone does not guarantee a usable split."""
    with pytest.raises(ValueError, match="did not reach its pre-registered targets"):
        assign(_corpus(3, 150), pilot_conversations=set(), seed=0)


def test_split_writer_exits_nonzero_on_a_corpus_too_small(tmp_path, csv_and_columns):
    import csv as _csv

    csv_path, cols = csv_and_columns
    rows = list(_csv.DictReader(csv_path.open(encoding="utf-8")))[:30]
    small = tmp_path / "small.csv"
    with small.open("w", newline="", encoding="utf-8") as fh:
        w = _csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    rc = split_main(
        ["--csv", str(small), "--columns", str(cols), "--out", str(tmp_path / "s.json"),
         "--runs-dir", str(tmp_path / "runs"), "--write"]
    )
    assert rc == 4
    assert not (tmp_path / "s.json").exists()


def test_split_reaches_its_targets_approximately():
    """Filling by conversation makes the targets approximate; it must not undershoot."""
    items = _corpus(200, 3)
    _, report = assign(items, pilot_conversations=set(), seed=0)
    assert report["counts"]["test"] >= TEST_ITEMS_TARGET
    assert report["counts"]["dev"] >= DEV_ITEMS_TARGET


def test_split_is_deterministic_under_a_seed():
    items = _corpus(140, 3)
    a, _ = assign(items, pilot_conversations=set(), seed=5)
    b, _ = assign(items, pilot_conversations=set(), seed=5)
    assert a == b


def test_split_differs_under_a_different_seed():
    items = _corpus(140, 3)
    a, _ = assign(items, pilot_conversations=set(), seed=1)
    b, _ = assign(items, pilot_conversations=set(), seed=2)
    assert a != b


def test_pilot_conversations_are_kept_out_of_test():
    """data-and-splits.md: EXP-000's pilot items must never enter the final test split."""
    items = _corpus(140, 3)
    pilots = {"conv-000", "conv-001", "conv-002"}
    assignment, report = assign(items, pilot_conversations=pilots, seed=0)
    for it in items:
        if it.conversation_id in pilots:
            assert assignment[it.item_id] == "train"
    assert report["pilot_conversations_excluded_from_test"] == 3


def test_split_writer_is_a_dry_run_by_default(tmp_path, csv_and_columns, capsys):
    csv_path, cols = csv_and_columns
    out = tmp_path / "split.json"
    rc = split_main(["--csv", str(csv_path), "--columns", str(cols), "--out", str(out)])
    assert rc == 0
    assert not out.exists(), "a frozen artifact must not be written without --write"
    assert "DRY RUN" in capsys.readouterr().out


def test_split_writer_warns_when_no_pilot_manifest_is_given(tmp_path, csv_and_columns, capsys):
    csv_path, cols = csv_and_columns
    split_main(["--csv", str(csv_path), "--columns", str(cols), "--out", str(tmp_path / "s.json")])
    assert "WARNING" in capsys.readouterr().out


def test_split_writer_refuses_to_overwrite(tmp_path, csv_and_columns):
    csv_path, cols = csv_and_columns
    out = tmp_path / "split.json"
    out.write_text("{}", encoding="utf-8")
    rc = split_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--out", str(out),
         "--runs-dir", str(tmp_path / "runs"), "--write"]
    )
    assert rc == 3, "the test split is frozen once created"


def test_split_writer_writes_and_records_its_hash(tmp_path, csv_and_columns):
    csv_path, cols = csv_and_columns
    out, runs = tmp_path / "split.json", tmp_path / "runs"
    rc = split_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--out", str(out),
         "--runs-dir", str(runs), "--write"]
    )
    assert rc == 0 and out.exists()
    cfg = json.loads(next(runs.rglob("config.json")).read_text())
    assert len(cfg["split_assignment_sha256"]) == 64
    assert cfg["step"] == "make_split"


# --- split loading --------------------------------------------------------------------------------

def test_unknown_split_name_is_refused(tmp_path):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"it-2": "trian"}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown split name"):
        load_split_assignment(p)


def test_unassigned_item_is_refused():
    """Dropping it silently would change the denominator without changing anything visible."""
    with pytest.raises(ValueError, match="no split assignment"):
        apply_split([item(2, "c", "m", "a", item_id="it-2")], {"other": "train"})


def test_of_split_filters(lexical_items):
    assignment = {it.item_id: ("test" if n < 10 else "train") for n, it in enumerate(lexical_items)}
    items = apply_split(lexical_items, assignment)
    assert len(of_split(items, "test")) == 10
    assert len(of_split(items, "train")) == len(lexical_items) - 10


def test_labelled_drops_unlabelled():
    assert len(labelled([item(2, "c", "m", "a"), item(3, "c", "m", "")])) == 1


# --- the CLI --------------------------------------------------------------------------------------

def _prepared(tmp_path: Path, csv_and_columns) -> tuple[Path, Path, Path]:
    csv_path, cols = csv_and_columns
    out, runs = tmp_path / "split.json", tmp_path / "runs"
    split_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--out", str(out),
         "--runs-dir", str(runs), "--write"]
    )
    return csv_path, cols, out


def test_stage1_writes_both_files(tmp_path, csv_and_columns):
    pytest.importorskip("sklearn")
    csv_path, cols, split = _prepared(tmp_path, csv_and_columns)
    runs = tmp_path / "runs2"
    rc = stage1_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(split),
         "--split", "dev", "--runs-dir", str(runs)]
    )
    assert rc == 0
    assert sorted(p.name for p in runs.rglob("*.json")) == ["config.json", "metrics.json"]


def test_stage1_names_the_floor_and_leaves_gate_2_pending(tmp_path, csv_and_columns):
    pytest.importorskip("sklearn")
    csv_path, cols, split = _prepared(tmp_path, csv_and_columns)
    runs = tmp_path / "runs2"
    stage1_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(split),
         "--split", "dev", "--runs-dir", str(runs)]
    )
    m = json.loads(next(runs.rglob("metrics.json")).read_text())
    assert m["floor_rung"] in ("B-triv-maj", "B-triv-lex")
    assert m["gate_2_condition_1"]["verdict"] == "NOT_ESTABLISHED"
    assert m["gate_2_condition_1"]["reason"] == "no_prompted_rung_yet"
    assert m["paired_lex_vs_maj"]["discordant"] >= 0


def test_stage1_refuses_per_item_output_for_test(tmp_path, csv_and_columns):
    """data-and-splits.md: a developer may see only aggregate metrics for test."""
    csv_path, cols, split = _prepared(tmp_path, csv_and_columns)
    rc = stage1_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(split),
         "--split", "test", "--runs-dir", str(tmp_path / "r"),
         "--per-item-out", str(tmp_path / "x.jsonl")]
    )
    assert rc == 2
    assert not (tmp_path / "x.jsonl").exists()


def test_stage1_writes_per_item_for_dev(tmp_path, csv_and_columns):
    pytest.importorskip("sklearn")
    csv_path, cols, split = _prepared(tmp_path, csv_and_columns)
    per_item = tmp_path / "dev.jsonl"
    stage1_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(split),
         "--split", "dev", "--runs-dir", str(tmp_path / "r"), "--per-item-out", str(per_item)]
    )
    rows = [json.loads(l) for l in per_item.read_text(encoding="utf-8").splitlines()]
    assert rows and {"item_id", "gold_action", "B-triv-maj", "B-triv-lex"} <= set(rows[0])


def test_stage1_output_passes_the_guard(tmp_path, csv_and_columns):
    pytest.importorskip("sklearn")
    csv_path, cols, split = _prepared(tmp_path, csv_and_columns)
    runs = tmp_path / "runs2"
    stage1_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(split),
         "--split", "dev", "--runs-dir", str(runs)]
    )
    for path in runs.rglob("*.json"):
        assert_output_safe(json.loads(path.read_text()), f"${path.name}")


def test_no_client_text_reaches_the_aggregates(tmp_path, csv_and_columns):
    """The same guarantee PE-001 asserts, re-asserted here: the guard is per-experiment."""
    pytest.importorskip("sklearn")
    csv_path, cols, split = _prepared(tmp_path, csv_and_columns)
    runs = tmp_path / "runs2"
    stage1_main(
        ["--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(split),
         "--split", "dev", "--runs-dir", str(runs)]
    )
    for path in runs.rglob("*.json"):
        text = path.read_text()
        assert SENTINEL not in text
        assert "price cost rupees" not in text, "a user message must not reach an aggregate file"


def test_guard_still_rejects_free_text():
    with pytest.raises(OutputSafetyError):
        assert_output_safe({"note": "the customer asked about parking"})
