"""Fabricated data for PE-002's tests. Nothing here is or resembles client text."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from data import Item  # noqa: E402
from scoring import Scored  # noqa: E402

SENTINEL = "ZZQQ-CLIENT-TEXT-SENTINEL-7391"
HEADER = ["conversation_id", "turn_index", "user_message", "action", "reply", "labeler", "item_id"]


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
        item_id=item_id or f"it-{row}",
        conversation_id=conv,
        turn_index=turn,
        user_message=msg,
        action=action,
        reply=reply,
        labeler=labeler,
        split=split,
    )


def scored(spec: list[tuple[str, str, bool]]) -> list[Scored]:
    """(item_id, conversation_id, correct) triples."""
    return [Scored(i, c, ok) for i, c, ok in spec]


@pytest.fixture
def lexical_items() -> list[Item]:
    """A corpus where the message text predicts the action perfectly, by construction.

    Two vocabularies that never overlap, so TF-IDF plus logistic regression should separate them
    and clearly beat a constant. That is what makes it a usable test of the lexical baseline: if
    the baseline cannot find a signal this blatant, it is broken rather than the data being hard.
    """
    items: list[Item] = []
    row = 2
    # 140 conversations x 3 turns = 420 items, about the size his ">400 examples" describes, so the
    # pre-registered 200 / 100 / remainder split is reachable in the tests that write one.
    for c in range(140):
        for t in range(1, 4):
            if (c + t) % 2 == 0:
                msg, act = f"price cost rupees budget {t}", "ask_budget"
            else:
                msg, act = f"visit site timing when {t}", "schedule_visit"
            items.append(item(row, f"conv-{c:03d}", msg, act, turn=t))
            row += 1
    return items


@pytest.fixture
def csv_and_columns(tmp_path: Path, lexical_items: list[Item]) -> tuple[Path, Path]:
    csv_path = tmp_path / "export.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=HEADER)
        w.writeheader()
        for it in lexical_items:
            w.writerow(
                {
                    "conversation_id": it.conversation_id,
                    "turn_index": it.turn_index,
                    "user_message": it.user_message,
                    "action": it.action,
                    "reply": it.reply,
                    "labeler": it.labeler,
                    "item_id": it.item_id,
                }
            )
    cols = tmp_path / "columns.yaml"
    cols.write_text(
        "\n".join(f"{k}: {k}" for k in HEADER) + "\n",
        encoding="utf-8",
    )
    return csv_path, cols
