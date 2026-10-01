"""Tests for the schema loader."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import schemas


def write_schema(path: Path, services: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(services), encoding="utf-8")
    return path


TRAIN = [
    {
        "service_name": "Banks_1",
        "description": "a bank",
        "slots": [
            {"name": "account_type", "description": "kind of account", "is_categorical": True,
             "possible_values": ["checking", "savings"]},
            {"name": "balance", "description": "money in the account"},
        ],
        "intents": [{"name": "CheckBalance", "description": "look up the balance"}],
    }
]


class TestLoadSchema:
    def test_parses_services_slots_and_intents(self, tmp_path):
        path = write_schema(tmp_path / "train" / "schema.json", TRAIN)
        services = schemas.load_schema(path)
        assert len(services) == 1
        service = services[0]
        assert service.name == "Banks_1"
        assert service.description == "a bank"
        assert [s.name for s in service.slots] == ["account_type", "balance"]
        assert [i.name for i in service.intents] == ["CheckBalance"]

    def test_records_position_for_the_sgd_x_one_to_one_mapping(self, tmp_path):
        path = write_schema(tmp_path / "schema.json", TRAIN)
        slots = schemas.all_slots(schemas.load_schema(path))
        assert [s.position for s in slots] == [0, 1]

    def test_slot_carries_its_service_and_description(self, tmp_path):
        path = write_schema(tmp_path / "schema.json", TRAIN)
        slot = schemas.all_slots(schemas.load_schema(path))[0]
        assert slot.service == "Banks_1"
        assert slot.description == "kind of account"
        assert slot.is_categorical is True

    def test_is_categorical_defaults_to_false_when_absent(self, tmp_path):
        path = write_schema(tmp_path / "schema.json", TRAIN)
        balance = schemas.all_slots(schemas.load_schema(path))[1]
        assert balance.is_categorical is False

    def test_rejects_a_file_that_is_not_a_list_of_services(self, tmp_path):
        path = tmp_path / "schema.json"
        path.write_text(json.dumps({"service_name": "Banks_1"}), encoding="utf-8")
        with pytest.raises(ValueError, match="expected a JSON list"):
            schemas.load_schema(path)


class TestPartitionTestServices:
    def test_splits_on_exact_service_name_membership(self, tmp_path):
        train = schemas.load_schema(write_schema(tmp_path / "train.json", TRAIN))
        test = schemas.load_schema(
            write_schema(
                tmp_path / "test.json",
                [
                    {"service_name": "Banks_1", "slots": [], "intents": []},
                    {"service_name": "Trains_1", "slots": [], "intents": []},
                ],
            )
        )
        seen, unseen = schemas.partition_test_services(train, test)
        assert [s.name for s in seen] == ["Banks_1"]
        assert [s.name for s in unseen] == ["Trains_1"]

    def test_a_versioned_sibling_counts_as_unseen(self, tmp_path):
        # Fixed in the experiment record: Restaurants_2 is unseen even with Restaurants_1
        # in train. This is the definition the gate's denominator depends on.
        train = schemas.load_schema(
            write_schema(tmp_path / "train.json",
                         [{"service_name": "Restaurants_1", "slots": [], "intents": []}])
        )
        test = schemas.load_schema(
            write_schema(tmp_path / "test.json",
                         [{"service_name": "Restaurants_2", "slots": [], "intents": []}])
        )
        seen, unseen = schemas.partition_test_services(train, test)
        assert seen == ()
        assert [s.name for s in unseen] == ["Restaurants_2"]


def test_sha256_file_matches_hashlib(tmp_path):
    path = tmp_path / "f.json"
    path.write_bytes(b'[{"service_name": "x", "slots": [], "intents": []}]')
    assert schemas.sha256_file(path) == hashlib.sha256(path.read_bytes()).hexdigest()
