"""Per-conversation placeholder assignment.

Scope is one conversation: counters reset for each, so the same person in two conversations
becomes `[PERSON_1]` in both and cannot be linked across them. Tokens are never hashes of the
original, because a hash is guessable from a small candidate set and leaks equality.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Replacement:
    category: str
    original: str
    token: str


_NON_DIGIT = re.compile(r"\D+")


def normalize(category: str, original: str) -> str:
    """Collapse surface variants so one real-world entity gets one token.

    Phones normalize to their last ten digits, so "+91 98765 43210" and "9876543210" share a
    token. Text-ish categories lowercase. Everything else is compared stripped.
    """
    value = original.strip()
    if category == "PHONE":
        digits = _NON_DIGIT.sub("", value)
        return digits[-10:] if len(digits) >= 10 else digits
    if category in {"EMAIL", "UPI", "PERSON", "IFSC"}:
        return value.lower()
    return value


class PlaceholderMap:
    """Assigns `[CATEGORY_n]` tokens, numbered by first appearance within one conversation."""

    def __init__(self) -> None:
        self._tokens: dict[tuple[str, str], str] = {}
        self._originals: dict[tuple[str, str], str] = {}
        self._counts: dict[str, int] = {}

    def token(self, category: str, original: str) -> str:
        key = (category, normalize(category, original))
        if key not in self._tokens:
            self._counts[category] = self._counts.get(category, 0) + 1
            self._tokens[key] = f"[{category}_{self._counts[category]}]"
            self._originals[key] = original.strip()
        return self._tokens[key]

    def index_of(self, category: str, original: str) -> int | None:
        """The ordinal already assigned to this entity, or None if it has not been seen."""
        key = (category, normalize(category, original))
        token = self._tokens.get(key)
        if token is None:
            return None
        return int(token.rsplit("_", 1)[1].rstrip("]"))

    def entries(self) -> list[Replacement]:
        return [
            Replacement(category=cat, original=self._originals[(cat, norm)], token=token)
            for (cat, norm), token in self._tokens.items()
        ]

    def counts(self) -> dict[str, int]:
        return dict(self._counts)
