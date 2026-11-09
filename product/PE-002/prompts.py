"""Prompt assembly and the prompt freeze.

PE-002's Setup: "the prompt is **frozen before any test item is scored**, iterated only on dev",
and "the prompt template is hashed into every run config. A `--split test` run requires
`--prompt-sha` and refuses to run unless it matches the template on disk."

The freeze is enforced here rather than trusted, because a prompt edited between the dev pass and
the test pass is the quietest way to turn a pre-registered comparison into a tuned one, and
nothing in the output would show it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from data import Item

# Which parts of the prompt each rung is allowed to change. Anything else is shared, so that a
# difference between two rungs is the thing the rung is defined to isolate and not an incidental
# wording change.
B0_PROMPT_FILE = "prompt_b0_shipped.md"
B1_PROMPT_FILE = "prompt_b1.md"


class PromptFreezeError(RuntimeError):
    """Raised when a test run's prompt does not match the hash it was pinned to."""


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PromptTemplate:
    path: Path
    text: str

    @classmethod
    def load(cls, path: Path) -> "PromptTemplate":
        if not path.exists():
            raise FileNotFoundError(
                f"{path} does not exist. B1's prompt is written by hand against the DEV split; "
                "see the run book. It is not generated."
            )
        return cls(path=path, text=path.read_text(encoding="utf-8"))

    @property
    def sha256(self) -> str:
        return sha256_text(self.text)

    def require_pinned(self, expected_sha: str | None, *, split: str) -> None:
        """On the test split, refuse unless the caller pinned this exact template.

        Pinning is required only for test. Dev is where iteration is supposed to happen, so
        requiring a hash there would make the intended workflow annoying for no gain.
        """
        if split != "test":
            return
        if not expected_sha:
            raise PromptFreezeError(
                "a --split test run requires --prompt-sha.\n"
                f"The template at {self.path} currently hashes to {self.sha256}.\n"
                "Pin it explicitly: that is what makes the pre-registered comparison checkable "
                "after the fact rather than a promise."
            )
        if expected_sha != self.sha256:
            raise PromptFreezeError(
                f"--prompt-sha does not match {self.path}.\n"
                f"  pinned:  {expected_sha}\n"
                f"  on disk: {self.sha256}\n"
                "The prompt changed since it was pinned. Either the change was not meant to reach "
                "the test pass, or the pass needs re-pre-registering in PE-002's Change log. "
                "Nothing has been sent."
            )


def render_vocabulary(vocabulary: set[str]) -> str:
    """The action vocabulary, as the prompt shows it. Sorted, so the prompt is deterministic."""
    return "\n".join(f"- {v}" for v in sorted(vocabulary))


def render_conversation(items: list[Item], target: Item) -> str:
    """The conversation up to and including the target message, as the labelling saw it.

    Ordered by `turn_index` where the sheet has one, else by row order, which `config.json` records
    as an assumption rather than a fact.
    """
    same = [i for i in items if i.conversation_id == target.conversation_id]
    ordered = sorted(
        same, key=lambda i: (i.turn_index if i.turn_index is not None else i.row, i.row)
    )
    lines: list[str] = []
    for it in ordered:
        lines.append(f"customer: {it.user_message}")
        if it.item_id == target.item_id:
            break
        if it.reply.strip():
            lines.append(f"bot: {it.reply}")
    return "\n".join(lines)


def select_fewshot(train: list[Item], *, k: int, seed: int) -> list[Item]:
    """B3's examples: k items from TRAIN only, drawn and ordered under a seed.

    Both the choice and the order are part of the result — few-shot accuracy moves with each — so
    the ids and their order go into the run config. One item per class first where possible, so a
    rare class is represented rather than crowded out by the majority; the remainder drawn at
    random.
    """
    import random

    rng = random.Random(seed)
    labelled = [i for i in train if i.action.strip() and i.user_message.strip()]
    if not labelled:
        raise ValueError("no labelled training items: cannot build a few-shot prompt")

    by_class: dict[str, list[Item]] = {}
    for it in labelled:
        by_class.setdefault(" ".join(it.action.split()).casefold(), []).append(it)

    chosen: list[Item] = []
    for cls in sorted(by_class):
        chosen.append(rng.choice(by_class[cls]))
        if len(chosen) >= k:
            break
    chosen = chosen[:k]

    if len(chosen) < k:
        picked = {i.item_id for i in chosen}
        rest = [i for i in labelled if i.item_id not in picked]
        rng.shuffle(rest)
        chosen.extend(rest[: k - len(chosen)])

    rng.shuffle(chosen)
    return chosen


def render_fewshot_block(items: list[Item], examples: list[Item]) -> str:
    parts: list[str] = []
    for n, ex in enumerate(examples, start=1):
        parts.append(
            f"Example {n}:\n{render_conversation(items, ex)}\n"
            f"action: {ex.action.strip()}"
        )
    return "\n\n".join(parts)


def build_prompt(
    template: PromptTemplate,
    *,
    items: list[Item],
    target: Item,
    vocabulary: set[str],
    fewshot: list[Item] | None,
) -> str:
    """Fill the template. Unknown placeholders are left alone rather than silently dropped.

    Placeholders: {{vocabulary}}, {{conversation}}, {{fewshot}}. A template that omits one simply
    does not use it — B0's shipped prompt, for instance, has no vocabulary block, which is part of
    what B1 is defined to add.
    """
    text = template.text
    text = text.replace("{{vocabulary}}", render_vocabulary(vocabulary))
    text = text.replace("{{conversation}}", render_conversation(items, target))
    text = text.replace(
        "{{fewshot}}", render_fewshot_block(items, fewshot) if fewshot else ""
    )
    return text
