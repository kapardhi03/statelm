"""Fabricated data for PE-001's tests.

Nothing here is or resembles client text. The strings are deliberately synthetic, and the sentinel
below exists so a test can assert that no field derived from message or reply text can reach an
output file.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit import Item  # noqa: E402

# A string that must never appear in metrics.json, config.json or the printed summary.
SENTINEL = "ZZQQ-CLIENT-TEXT-SENTINEL-7391"


def item(
    row: int,
    conv: str,
    msg: str,
    action: str,
    *,
    reply: str = "ok",
    labeler: str = "human",
    turn: int | None = None,
    item_id: str | None = None,
    split: str | None = None,
) -> Item:
    return Item(
        row=row,
        item_id=item_id or f"row-{row}",
        conversation_id=conv,
        turn_index=turn,
        user_message=msg,
        action=action,
        reply=reply,
        labeler=labeler,
        split=split,
    )


@pytest.fixture
def simple_items() -> list[Item]:
    """Two conversations, three actions, one message repeated with two different actions.

    Counts a test can rely on: 6 rows, 2 conversations, action a=3 / b=2 / c=1, and the message
    "same question" appears twice with different actions, so the memory-dependence lower bound
    sees one ambiguous group of 2 items.
    """
    return [
        item(2, "c1", "hello there", "a", turn=1),
        item(3, "c1", "same question", "a", turn=2),
        item(4, "c1", "what is the price", "b", turn=3),
        item(5, "c2", "same question", "b", turn=1),
        item(6, "c2", "another one", "a", turn=2),
        item(7, "c2", "and one more", "c", turn=3),
    ]


@pytest.fixture
def sentinel_items() -> list[Item]:
    """Items whose client-text fields carry the sentinel.

    The `action` column deliberately does NOT: PE-001 emits the action taxonomy on purpose, because
    it is the answer to Q18 and the class distribution is unreadable without it. An annotation
    label is Kapardhi's own vocabulary, not conversation text. What guards the case where that
    column turns out to hold free-form notes is `safety.class_names_safe_to_emit`, which
    `sentence_action_items` exercises.
    """
    return [
        item(
            2 + n,
            f"conv-{SENTINEL}-{n}",
            f"message {SENTINEL} {n}",
            "ask_budget",
            reply=f"reply {SENTINEL} {n}",
            labeler=f"labeler-{SENTINEL}",
            item_id=f"id-{SENTINEL}-{n}",
            turn=1,
        )
        for n in range(12)
    ]


@pytest.fixture
def sentence_action_items() -> list[Item]:
    """An `action` column holding free-form notes rather than a closed class set.

    This is the case the class-label guard exists for: a note about a conversation can quote the
    customer, so the names must be withheld and replaced by hashes.
    """
    return [
        item(2 + n, f"c{n}", f"message {n}", f"he asked about {SENTINEL}, so I replied.", turn=1)
        for n in range(12)
    ]


def write_csv(path: Path, rows: list[dict[str, str]], header: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    return path


@pytest.fixture
def columns_yaml(tmp_path: Path) -> Path:
    p = tmp_path / "columns.yaml"
    p.write_text(
        "\n".join(
            [
                "conversation_id: conversation_id",
                "user_message: user_message",
                "action: action",
                "turn_index: turn_index",
                "reply: reply",
                "labeler: labeler",
                "item_id: item_id",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return p
