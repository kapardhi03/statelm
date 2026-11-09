"""Fabricated data for PE-003's tests. Nothing here is or resembles client text."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "PE-002"))

from data import Item  # noqa: E402
from dataset import Example  # noqa: E402


def item(row: int, conv: str, msg: str, action: str, *, reply: str = "ok",
         turn: int | None = None, split: str | None = None) -> Item:
    return Item(row=row, item_id=f"it-{row}", conversation_id=conv, turn_index=turn,
                user_message=msg, action=action, reply=reply, labeler="human", split=split)


@pytest.fixture
def example() -> Example:
    return Example("it-2", "conv-1", "a prompt of several words here", "ask_budget")


@pytest.fixture
def train_items() -> list[Item]:
    out = []
    row = 2
    for c in range(8):
        for cls in ("ask_budget", "schedule_visit"):
            out.append(item(row, f"conv-{c}", f"message {row} words here", cls, turn=1))
            row += 1
    return out
