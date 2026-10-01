"""Load SGD / SGD-X schema files for EXP-002, with provenance.

Reads schema JSON only: no dialogue files, no state annotations, no labels. Each schema
file is a JSON list of services, each service carrying `service_name`, `description`,
`slots` and `intents`.

`position` is recorded on every slot and intent because H2 pairs each SGD-X variant slot
with its own original slot by (service_name, position in that service's slot list). Names
cannot serve as the key there: paraphrasing the names is the whole point of SGD-X.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Slot:
    service: str
    name: str
    description: str
    is_categorical: bool
    position: int


@dataclass(frozen=True)
class Intent:
    service: str
    name: str
    description: str
    position: int


@dataclass(frozen=True)
class Service:
    name: str
    description: str
    slots: tuple[Slot, ...]
    intents: tuple[Intent, ...]


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_schema(path: Path) -> tuple[Service, ...]:
    """Parse one schema.json into Services, preserving file order."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected a JSON list of services, got {type(raw).__name__}")
    services: list[Service] = []
    for entry in raw:
        name = entry["service_name"]
        services.append(
            Service(
                name=name,
                description=entry.get("description", ""),
                slots=tuple(
                    Slot(
                        service=name,
                        name=slot["name"],
                        description=slot.get("description", ""),
                        is_categorical=bool(slot.get("is_categorical", False)),
                        position=i,
                    )
                    for i, slot in enumerate(entry.get("slots", []))
                ),
                intents=tuple(
                    Intent(
                        service=name,
                        name=intent["name"],
                        description=intent.get("description", ""),
                        position=i,
                    )
                    for i, intent in enumerate(entry.get("intents", []))
                ),
            )
        )
    return tuple(services)


def all_slots(services: tuple[Service, ...]) -> tuple[Slot, ...]:
    return tuple(slot for service in services for slot in service.slots)


def all_intents(services: tuple[Service, ...]) -> tuple[Intent, ...]:
    return tuple(intent for service in services for intent in service.intents)


def partition_test_services(
    train: tuple[Service, ...], test: tuple[Service, ...]
) -> tuple[tuple[Service, ...], tuple[Service, ...]]:
    """Split test services into (seen, unseen) by exact service_name membership in train.

    This is the operational definition of "unseen service" fixed in the experiment record:
    a versioned sibling counts as unseen, so `Restaurants_2` is unseen even though
    `Restaurants_1` is in train.
    """
    train_names = {service.name for service in train}
    seen = tuple(s for s in test if s.name in train_names)
    unseen = tuple(s for s in test if s.name not in train_names)
    return seen, unseen
