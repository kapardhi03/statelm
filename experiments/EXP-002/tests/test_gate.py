"""End-to-end tests for the Step 1 gate, on hand-built fixtures with known counts.

This is the test that guards the headline number: a refactor that silently changes what
the gate counts fails here rather than producing a different plausible percentage.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import run_sanity_check
import schemas

# Train: 4 slot names, 3 intent names.
TRAIN = [
    {
        "service_name": "Banks_1",
        "slots": [{"name": "account_type", "description": "d"}, {"name": "balance", "description": "d"}],
        "intents": [{"name": "CheckBalance", "description": "d"}, {"name": "TransferMoney", "description": "d"}],
    },
    {
        "service_name": "Hotels_1",
        "slots": [{"name": "location", "description": "d"}, {"name": "star_rating", "description": "d"}],
        "intents": [{"name": "ReserveHotel", "description": "d"}],
    },
]

# Test: one seen service (excluded from the gate population) and one unseen service whose
# slots match train 2 out of 3, and whose intents match 2 out of 3. Both land in band.
TEST_PASSING = [
    {
        "service_name": "Banks_1",
        "slots": [{"name": "never_counted", "description": "d"}],
        "intents": [{"name": "NeverCounted", "description": "d"}],
    },
    {
        "service_name": "Buses_3",
        "slots": [
            {"name": "account_type", "description": "d"},
            {"name": "location", "description": "d"},
            {"name": "seat_class", "description": "d"},
        ],
        "intents": [
            {"name": "CheckBalance", "description": "d"},
            {"name": "ReserveHotel", "description": "d"},
            {"name": "BuyBusTicket", "description": "d"},
        ],
    },
]

# Test: one unseen service matching 1 of 3 slots, well below the band.
TEST_FAILING = [
    {
        "service_name": "Buses_3",
        "slots": [
            {"name": "account_type", "description": "d"},
            {"name": "brand_new_one", "description": "d"},
            {"name": "brand_new_two", "description": "d"},
        ],
        "intents": [
            {"name": "CheckBalance", "description": "d"},
            {"name": "BrandNewIntent", "description": "d"},
            {"name": "AnotherNewIntent", "description": "d"},
        ],
    }
]


def build_data_root(tmp_path: Path, test_services: list[dict]) -> Path:
    root = tmp_path / "data"
    for split, services in (("train", TRAIN), ("test", test_services)):
        path = root / split / "schema.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(services), encoding="utf-8")
    return root


def run_gate(tmp_path: Path, test_services: list[dict], monkeypatch) -> dict:
    data_root = build_data_root(tmp_path, test_services)
    out_root = tmp_path / "runs"
    monkeypatch.setattr(
        "sys.argv",
        [
            "run_sanity_check.py",
            "--data-root", str(data_root),
            "--out-root", str(out_root),
            "--dataset-commit", "deadbeef",
            "--run-id", "test-run",
        ],
    )
    assert run_sanity_check.main() == 0
    return json.loads((out_root / "test-run" / "sanity_check.json").read_text())


class TestGateMath:
    def test_passing_fixture(self, tmp_path, monkeypatch):
        result = run_gate(tmp_path, TEST_PASSING, monkeypatch)
        assert result["gate"]["slots"]["matched"] == 2
        assert result["gate"]["slots"]["total"] == 3
        assert result["gate"]["slots"]["rate_percent"] == pytest.approx(200 / 3, abs=1e-3)
        assert result["gate"]["intents"]["matched"] == 2
        assert result["gate"]["intents"]["total"] == 3
        assert result["gate"]["pass"] is True

    def test_seen_service_slots_are_excluded_from_the_gate_population(self, tmp_path, monkeypatch):
        result = run_gate(tmp_path, TEST_PASSING, monkeypatch)
        assert result["populations"]["seen_test_services"] == ["Banks_1"]
        assert result["populations"]["unseen_test_services"] == ["Buses_3"]
        # 3, not 4: the seen service's slot never enters the denominator.
        assert result["populations"]["unseen_slot_instances"] == 3
        names = [e["name"] for e in result["evidence"]["slots_N0_instances"]["matched"]]
        assert "never_counted" not in names

    def test_failing_fixture_reports_fail_without_raising(self, tmp_path, monkeypatch):
        result = run_gate(tmp_path, TEST_FAILING, monkeypatch)
        assert result["gate"]["slots"]["rate_percent"] == pytest.approx(100 / 3, abs=1e-3)
        assert result["gate"]["pass"] is False
        assert result["gate"]["slots"]["in_band"] is False

    def test_evidence_lists_reconcile_with_the_rate(self, tmp_path, monkeypatch):
        result = run_gate(tmp_path, TEST_PASSING, monkeypatch)
        ev = result["evidence"]["slots_N0_instances"]
        assert len(ev["matched"]) == result["gate"]["slots"]["matched"]
        assert len(ev["matched"]) + len(ev["unmatched"]) == result["gate"]["slots"]["total"]
        assert [e["name"] for e in ev["unmatched"]] == ["seat_class"]

    def test_evidence_names_the_train_services_a_match_came_from(self, tmp_path, monkeypatch):
        result = run_gate(tmp_path, TEST_PASSING, monkeypatch)
        matched = {e["name"]: e["train_services"] for e in result["evidence"]["slots_N0_instances"]["matched"]}
        assert matched["account_type"] == ["Banks_1"]
        assert matched["location"] == ["Hotels_1"]


class TestRunArtifacts:
    def test_config_records_provenance_and_thresholds(self, tmp_path, monkeypatch):
        data_root = build_data_root(tmp_path, TEST_PASSING)
        out_root = tmp_path / "runs"
        monkeypatch.setattr(
            "sys.argv",
            ["run_sanity_check.py", "--data-root", str(data_root), "--out-root", str(out_root),
             "--dataset-commit", "deadbeef", "--run-id", "test-run"],
        )
        run_sanity_check.main()
        config = json.loads((out_root / "test-run" / "config.json").read_text())
        assert config["experiment"] == "EXP-002"
        assert config["dataset"]["commit"] == "deadbeef"
        assert config["dataset"]["files_read"]["train/schema.json"] == schemas.sha256_file(
            data_root / "train" / "schema.json"
        )
        assert config["thresholds"]["gate_slot_band_percent"] == [60.0, 70.0]
        assert config["thresholds"]["gate_intent_band_percent"] == [66.0, 76.0]
        # The gate embeds nothing, and says so rather than implying a model was used.
        assert config["embedding_models"] is None
        assert len(config["input_template_hash"]) == 64
        assert config["seed"] == 0

    def test_writes_the_three_expected_files(self, tmp_path, monkeypatch):
        run_gate(tmp_path, TEST_PASSING, monkeypatch)
        run_dir = tmp_path / "runs" / "test-run"
        assert sorted(p.name for p in run_dir.iterdir()) == ["config.json", "log.txt", "sanity_check.json"]

    def test_secondary_cells_cover_both_other_pipelines_and_units(self, tmp_path, monkeypatch):
        result = run_gate(tmp_path, TEST_PASSING, monkeypatch)
        cells = {(c["kind"], c["pipeline"], c["unit"]) for c in result["secondary_non_gating"]}
        assert ("slots", "N1", "instances") in cells
        assert ("slots", "N0", "unique") in cells
        assert ("intents", "N2", "unique") in cells
        # The gate cell itself is not duplicated into the secondary list.
        assert ("slots", "N0", "instances") not in cells


def test_empty_unseen_population_stops_rather_than_reporting_zero(tmp_path, monkeypatch):
    # Every test service is also in train, so the gate population is empty. A 0.0% gate
    # would read as a refutation; this must fail loudly instead.
    data_root = build_data_root(tmp_path, [{"service_name": "Banks_1", "slots": [], "intents": []}])
    monkeypatch.setattr(
        "sys.argv",
        ["run_sanity_check.py", "--data-root", str(data_root), "--out-root", str(tmp_path / "runs"),
         "--dataset-commit", "deadbeef", "--run-id", "test-run"],
    )
    with pytest.raises(SystemExit, match="no unseen-service slots"):
        run_sanity_check.main()
