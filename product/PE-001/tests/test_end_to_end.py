"""The CLI, end to end, on a fabricated CSV. No model, no network, no client text.

Also the column mapping and the context-stripped re-label sheet, because both are places where a
mistake would be quiet: a wrong mapping produces plausible numbers from the wrong columns, and a
pre-filled action column in the re-label sheet would break CLAUDE.md rule 3.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest
from conftest import SENTINEL, write_csv

from columns import Columns
from run_audit import main, write_recheck_sample
from thresholds import RECHECK_SAMPLE_N

HEADER = ["conversation_id", "turn_index", "user_message", "action", "reply", "labeler", "item_id"]


def _rows(n: int = 12, *, sentinel: bool = False) -> list[dict[str, str]]:
    tag = SENTINEL if sentinel else "msg"
    return [
        {
            "conversation_id": f"c{i // 3}",
            "turn_index": str(i % 3 + 1),
            "user_message": f"{tag} number {i}",
            "action": f"act_{i % 3}",
            "reply": f"{tag} reply {i}",
            "labeler": "human",
            "item_id": f"it-{i}",
        }
        for i in range(n)
    ]


def test_print_columns_reads_no_data_row(tmp_path, capsys):
    csv_path = write_csv(tmp_path / "e.csv", _rows(sentinel=True), HEADER)
    rc = main(["--print-columns", "--csv", str(csv_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "user_message" in out
    assert SENTINEL not in out, "only the header row may be printed"


def test_audit_writes_both_files(tmp_path, columns_yaml):
    csv_path = write_csv(tmp_path / "e.csv", _rows(), HEADER)
    runs = tmp_path / "runs"
    rc = main(["--csv", str(csv_path), "--columns", str(columns_yaml), "--runs-dir", str(runs)])
    assert rc == 0
    produced = sorted(p.name for p in runs.rglob("*.json"))
    assert produced == ["config.json", "metrics.json"]


def test_config_records_what_a_rerun_would_need(tmp_path, columns_yaml):
    csv_path = write_csv(tmp_path / "e.csv", _rows(), HEADER)
    runs = tmp_path / "runs"
    main(["--csv", str(csv_path), "--columns", str(columns_yaml), "--runs-dir", str(runs)])
    cfg = json.loads(next(runs.rglob("config.json")).read_text())
    for key in (
        "run_id",
        "git_commit",
        "git_tree_dirty",
        "seed",
        "input_sha256",
        "input_rows",
        "columns_sha256",
        "thresholds",
        "script_version",
    ):
        assert key in cfg, key
    assert cfg["input_rows"] == 12
    assert cfg["turn_order_from"] == "turn_index"
    assert cfg["exp000_manifest_supplied"] is False


def test_no_sentinel_reaches_either_file_or_stdout(tmp_path, columns_yaml, capsys):
    csv_path = write_csv(tmp_path / "e.csv", _rows(sentinel=True), HEADER)
    runs = tmp_path / "runs"
    main(["--csv", str(csv_path), "--columns", str(columns_yaml), "--runs-dir", str(runs)])
    printed = capsys.readouterr().out
    assert SENTINEL not in printed
    for path in runs.rglob("*.json"):
        assert SENTINEL not in path.read_text(), path.name


def test_turn_order_falls_back_and_records_the_fallback(tmp_path):
    header = [h for h in HEADER if h != "turn_index"]
    rows = [{k: v for k, v in r.items() if k != "turn_index"} for r in _rows()]
    csv_path = write_csv(tmp_path / "e.csv", rows, header)
    cols = tmp_path / "columns.yaml"
    cols.write_text(
        "conversation_id: conversation_id\nuser_message: user_message\naction: action\n"
        "reply: reply\nlabeler: labeler\nitem_id: item_id\n",
        encoding="utf-8",
    )
    runs = tmp_path / "runs"
    assert main(["--csv", str(csv_path), "--columns", str(cols), "--runs-dir", str(runs)]) == 0
    cfg = json.loads(next(runs.rglob("config.json")).read_text())
    assert cfg["turn_order_from"] == "export_row_order"


def test_missing_csv_is_an_error(tmp_path, columns_yaml):
    rc = main(["--csv", str(tmp_path / "nope.csv"), "--columns", str(columns_yaml)])
    assert rc == 2


def test_columns_required_without_print_columns(tmp_path):
    csv_path = write_csv(tmp_path / "e.csv", _rows(), HEADER)
    assert main(["--csv", str(csv_path)]) == 2


def test_empty_export_is_an_error(tmp_path, columns_yaml):
    csv_path = write_csv(tmp_path / "e.csv", [], HEADER)
    assert main(["--csv", str(csv_path), "--columns", str(columns_yaml)]) == 2


# --- the column mapping ---------------------------------------------------------------------------

def test_mapping_error_names_the_exports_real_headers(tmp_path):
    cols = Columns(conversation_id="conv", user_message="msg", action="act")
    with pytest.raises(ValueError) as exc:
        cols.validate_against(["conversation_id", "user_message", "action"])
    msg = str(exc.value)
    assert "conv" in msg and "conversation_id" in msg


def test_required_fields_must_be_set(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text("user_message: m\naction: a\n", encoding="utf-8")
    with pytest.raises(ValueError, match="required"):
        Columns.load(p)


def test_unknown_logical_field_is_rejected(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(
        "conversation_id: c\nuser_message: m\naction: a\nsentiment: s\n", encoding="utf-8"
    )
    with pytest.raises(ValueError, match="unknown logical field"):
        Columns.load(p)


def test_mapping_hash_is_stable_and_order_independent():
    a = Columns(conversation_id="c", user_message="m", action="a", reply="r")
    b = Columns(action="a", user_message="m", conversation_id="c", reply="r")
    assert a.sha256() == b.sha256()
    c = Columns(conversation_id="c", user_message="m", action="a", reply="other")
    assert a.sha256() != c.sha256()


def test_the_shipped_example_mapping_loads():
    """So the file a reader copies is not itself broken."""
    example = Path(__file__).resolve().parents[1] / "columns.example.yaml"
    cols = Columns.load(example)
    assert cols.conversation_id and cols.user_message and cols.action


# --- the context-stripped re-label sheet ----------------------------------------------------------

def test_recheck_sample_leaves_the_action_column_empty(tmp_path, simple_items):
    out = tmp_path / "recheck.csv"
    write_recheck_sample(simple_items, out, seed=0)
    rows = list(csv.DictReader(out.open(encoding="utf-8")))
    assert rows, "sample must not be empty"
    assert all(r["action_without_context"] == "" for r in rows), (
        "pre-filling a label is pre-labelling, which CLAUDE.md rule 3 forbids"
    )


def test_recheck_sample_keeps_the_answer_key_in_a_separate_file(tmp_path, simple_items):
    out = tmp_path / "recheck.csv"
    write_recheck_sample(simple_items, out, seed=0)
    key = out.with_name("recheck.key.csv")
    assert key.exists()
    assert "original_action" not in out.read_text(encoding="utf-8")
    assert "original_action" in key.read_text(encoding="utf-8")


def test_recheck_sample_is_deterministic_under_a_seed(tmp_path, simple_items):
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_recheck_sample(simple_items, a, seed=7)
    write_recheck_sample(simple_items, b, seed=7)
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")


def test_recheck_sample_differs_under_a_different_seed(tmp_path):
    from conftest import item

    items = [item(2 + n, f"c{n}", f"message {n}", "a") for n in range(60)]
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    write_recheck_sample(items, a, seed=1)
    write_recheck_sample(items, b, seed=2)
    assert a.read_text(encoding="utf-8") != b.read_text(encoding="utf-8")


def test_recheck_sample_respects_the_pre_registered_size(tmp_path):
    from conftest import item

    items = [item(2 + n, f"c{n}", f"message {n}", "a") for n in range(200)]
    out = tmp_path / "r.csv"
    n = write_recheck_sample(items, out, seed=0)
    assert n == RECHECK_SAMPLE_N


def test_recheck_sample_handles_a_corpus_smaller_than_the_sample(tmp_path, simple_items):
    out = tmp_path / "r.csv"
    n = write_recheck_sample(simple_items, out, seed=0)
    assert n == len(simple_items)
