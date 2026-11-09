"""Loading the labelled export and the frozen split, for PE-002.

Self-contained, as each experiment directory in this repository is: `columns.py`, `normalize.py`,
`provenance.py` and `safety.py` are copies of PE-001's rather than imports from it. EXP-003's
record already put that choice to Kapardhi — promote to a shared module on the second reuse, or
copy and accept the duplication — and it is still his. This is the second reuse, so the question is
live; copying keeps PE-001's tests green either way and is the reversible option.
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from columns import Columns

VALID_SPLITS = ("train", "dev", "test")


@dataclass(frozen=True)
class Item:
    """One labelled user message."""

    row: int
    item_id: str
    conversation_id: str
    turn_index: int | None
    user_message: str
    action: str
    reply: str
    labeler: str
    split: str | None = None


def read_items(csv_path: Path, cols: Columns) -> list[Item]:
    items: list[Item] = []
    with csv_path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        cols.validate_against(list(reader.fieldnames or []))
        for row_no, row in enumerate(reader, start=2):
            def get(field: str) -> str:
                name = getattr(cols, field)
                return (row.get(name) or "").strip() if name else ""

            raw_turn = get("turn_index")
            try:
                turn = int(raw_turn) if raw_turn else None
            except ValueError:
                turn = None

            items.append(
                Item(
                    row=row_no,
                    item_id=get("item_id") or f"row-{row_no}",
                    conversation_id=get("conversation_id"),
                    turn_index=turn,
                    user_message=get("user_message"),
                    action=get("action"),
                    reply=get("reply"),
                    labeler=get("labeler"),
                )
            )
    return items


def load_split_assignment(path: Path) -> dict[str, str]:
    """Read `item_id -> split`, and refuse anything that is not one of the three splits.

    A typo in a split name would silently empty a split and make every number that follows describe
    the wrong population, so it fails here instead.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: expected a mapping of item_id -> split")
    assignment = {str(k): str(v) for k, v in payload.items()}
    bad = sorted({v for v in assignment.values() if v not in VALID_SPLITS})
    if bad:
        raise ValueError(f"{path}: unknown split name(s) {bad}; expected one of {list(VALID_SPLITS)}")
    return assignment


def apply_split(items: list[Item], assignment: dict[str, str]) -> list[Item]:
    """Attach splits, and refuse if any item is unassigned.

    An unassigned item would otherwise be dropped from every rung quietly, which changes the
    denominator without changing anything visible.
    """
    missing = [i.item_id for i in items if i.item_id not in assignment]
    if missing:
        raise ValueError(
            f"{len(missing)} item(s) have no split assignment, e.g. {missing[:3]}. "
            "Re-run make_split.py against this export, or pass the matching assignment file."
        )
    return [
        Item(**{**it.__dict__, "split": assignment[it.item_id]}) for it in items
    ]


def of_split(items: list[Item], split: str) -> list[Item]:
    if split not in VALID_SPLITS:
        raise ValueError(f"unknown split {split!r}; expected one of {list(VALID_SPLITS)}")
    return [i for i in items if i.split == split]


def labelled(items: list[Item]) -> list[Item]:
    """Items with an `action`. Unlabelled rows are training candidates at most, never scored."""
    return [i for i in items if i.action.strip()]
