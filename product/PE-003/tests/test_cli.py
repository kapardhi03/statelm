"""PE-003's gates and the end-to-end stub run.

Three preconditions are enforced in code, and all three are tested: PE-002's Gate 2 must have
passed on both conditions, the Q9 consent record must name every provider the run would reach, and
a test-split run must pin the prompt by hash.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from run_finetune import check_gate_two, main, predictions_from

HEADER = ["conversation_id", "turn_index", "user_message", "action", "reply", "labeler", "item_id"]
PE002 = Path(__file__).resolve().parents[2] / "PE-002"


# --- the Gate 2 gate ------------------------------------------------------------------------------

def _gate_file(tmp_path: Path, overall: str, conditions: dict) -> Path:
    p = tmp_path / "gate2.json"
    p.write_text(json.dumps({"gate_2": {"overall": overall, "conditions": conditions}}), "utf-8")
    return p


def test_gate_two_is_required():
    with pytest.raises(RuntimeError, match="--gate2-metrics is required"):
        check_gate_two(None)


def test_gate_two_must_have_passed_both_conditions(tmp_path):
    p = _gate_file(tmp_path, "PASS", {"a": {"verdict": "PASS"}, "b": {"verdict": "PASS"}})
    out = check_gate_two(p)
    assert out["gate2_overall"] == "PASS"
    assert len(out["gate2_source_sha256"]) == 64


def test_a_failed_condition_blocks_the_fine_tune(tmp_path):
    """If the pattern is lexical, the track ends rather than fine-tuning."""
    p = _gate_file(tmp_path, "FAIL", {"1": {"verdict": "FAIL"}, "2": {"verdict": "PASS"}})
    with pytest.raises(RuntimeError, match="did not pass"):
        check_gate_two(p)


def test_a_not_established_condition_blocks_it_too(tmp_path):
    """NOT_ESTABLISHED means the measurement it needs has not been made."""
    p = _gate_file(tmp_path, "NOT_ESTABLISHED",
                   {"1": {"verdict": "PASS"}, "2": {"verdict": "NOT_ESTABLISHED"}})
    with pytest.raises(RuntimeError, match="did not pass"):
        check_gate_two(p)


def test_an_overall_pass_with_a_failing_row_still_blocks(tmp_path):
    """The rows decide, not the summary line."""
    p = _gate_file(tmp_path, "PASS", {"1": {"verdict": "PASS"}, "2": {"verdict": "FAIL"}})
    with pytest.raises(RuntimeError, match="not passing"):
        check_gate_two(p)


# --- prediction parsing ---------------------------------------------------------------------------

def test_predictions_take_the_first_line(train_items):
    preds = predictions_from(["ask_budget\nand some chatter"], train_items[:1], {"ask_budget"})
    assert preds[0].predicted == "ask_budget"


def test_predictions_strip_an_action_prefix(train_items):
    preds = predictions_from(["action: schedule_visit"], train_items[:1], {"schedule_visit"})
    assert preds[0].predicted == "schedule_visit"


def test_an_empty_sample_is_an_empty_prediction(train_items):
    preds = predictions_from([""], train_items[:1], {"a"})
    assert preds[0].predicted == ""
    assert preds[0].correct is False


# --- end to end, offline --------------------------------------------------------------------------

@pytest.fixture
def corpus(tmp_path: Path) -> tuple[Path, Path, Path]:
    """A corpus big enough for the pre-registered split, written as a CSV plus its split file."""
    rows, split = [], {}
    n = 0
    for c in range(140):
        for t in range(1, 4):
            n += 1
            item_id = f"it-{n}"
            cls = "ask_budget" if (c + t) % 2 == 0 else "schedule_visit"
            rows.append({
                "conversation_id": f"conv-{c:03d}", "turn_index": str(t),
                "user_message": f"message {n} with a few words", "action": cls,
                "reply": "noted", "labeler": "human", "item_id": item_id,
            })
            split[item_id] = "test" if c < 70 else ("dev" if c < 105 else "train")
    csv_path = tmp_path / "export.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        w.writerows(rows)
    cols = tmp_path / "columns.yaml"
    cols.write_text("\n".join(f"{k}: {k}" for k in HEADER) + "\n", encoding="utf-8")
    sp = tmp_path / "split.json"
    sp.write_text(json.dumps(split), encoding="utf-8")
    return csv_path, cols, sp


def _args(corpus, tmp_path, *extra):
    csv_path, cols, sp = corpus
    return [
        "--csv", str(csv_path), "--columns", str(cols), "--split-assignment", str(sp),
        "--providers", str(PE002 / "providers.example.yaml"),
        "--consent", str(tmp_path / "no-consent.yaml"),
        "--runs-dir", str(tmp_path / "runs"), *extra,
    ]


def test_stub_run_writes_both_files(corpus, tmp_path):
    rc = main(_args(corpus, tmp_path, "--stub", "--split", "dev", "--max-epochs", "2"))
    assert rc == 0
    produced = sorted(p.name for p in (tmp_path / "runs").rglob("*.json"))
    assert produced == ["config.json", "metrics.json"]


def test_the_config_carries_the_loss_mask_totals(corpus, tmp_path):
    """The pre-registered check's output. A run that failed it would not have reached this file."""
    main(_args(corpus, tmp_path, "--stub", "--split", "dev", "--max-epochs", "2"))
    cfg = json.loads(next((tmp_path / "runs").rglob("config.json")).read_text())
    mask = cfg["loss_mask"]
    assert mask["weighted_tokens_total"] > 0
    assert mask["positions_total"] > mask["weighted_tokens_total"]
    assert 0 < mask["weighted_share"] < 1
    assert cfg["lora_rank"] == 32
    assert cfg["primary_seed"] == 0


def test_the_metrics_carry_a_verdict_and_the_sweep(corpus, tmp_path):
    main(_args(corpus, tmp_path, "--stub", "--split", "dev", "--max-epochs", "2"))
    m = json.loads(next((tmp_path / "runs").rglob("metrics.json")).read_text())
    assert m["verdict"]["verdict"] in ("PASS", "FAIL", "UNSTABLE", "NOT_ESTABLISHED")
    assert m["sweep"]["chosen_learning_rate"] > 0
    assert len(m["fine_tune_per_seed"]) == 3, "the chosen LR's three seeds are scored"
    assert m["reply_metric"] is None, "no reply metric until Q19"


def test_the_with_reply_configuration_is_labelled(corpus, tmp_path):
    main(_args(corpus, tmp_path, "--stub", "--split", "dev", "--max-epochs", "1", "--with-reply"))
    m = json.loads(next((tmp_path / "runs").rglob("metrics.json")).read_text())
    assert m["configuration"] == "action_and_reply"


def test_a_real_run_refuses_without_gate_two(corpus, tmp_path):
    assert main(_args(corpus, tmp_path, "--split", "dev")) == 8


def test_a_real_run_refuses_without_consent(corpus, tmp_path):
    gate = _gate_file(tmp_path, "PASS", {"1": {"verdict": "PASS"}, "2": {"verdict": "PASS"}})
    rc = main(_args(corpus, tmp_path, "--split", "dev", "--gate2-metrics", str(gate)))
    assert rc == 6


def test_a_test_split_run_refuses_without_a_pinned_prompt(corpus, tmp_path):
    assert main(_args(corpus, tmp_path, "--stub", "--split", "test")) == 5


def test_nothing_was_written_by_a_refused_run(corpus, tmp_path):
    main(_args(corpus, tmp_path, "--split", "dev"))
    assert not list((tmp_path / "runs").rglob("*.json"))
