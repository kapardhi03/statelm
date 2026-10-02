"""Value normalization for EXP-000's value-agreement figures. Pure functions.

Two normalizations, reported separately and never merged:

- **strict** (primary): case, surrounding whitespace, internal whitespace runs and trailing
  punctuation. Nothing else. "40-45 lakhs" and "40 to 45 lakhs" are *different* values under
  this rule, which is the point: it is a lower bound on value agreement that cannot flatter the
  annotators.
- **number_aware** (secondary): the numbers in the value, with Indian magnitude words resolved,
  compared alongside whatever words are left over. "40-45 lakhs", "40 to 45 lakhs" and
  "40-45 L" all reduce to the same thing. Decided by Kapardhi, 2026-10-02 (Q4).

What number_aware deliberately does NOT do: drop hedge words. "around 40 lakhs" and "40 lakhs"
stay different, because HEDGED is a label of its own and collapsing them here would hide the
distinction the experiment is trying to measure.

What it can get wrong: the residual words are compared as a set of tokens, so "3BHK flat" and
"3 bedroom flat" are correctly different, but a value whose meaning lives in word order is not
protected. That is a cost of a secondary figure, which is why it is secondary.
"""

from __future__ import annotations

import re
import unicodedata

import thresholds

#: Dashes that mean "to" in a range, including the unicode ones a spreadsheet produces.
_DASHES = "‐‑‒–—―−"

#: Dropped before comparison: currency markers and the words that join the ends of a range.
_CURRENCY = ("₹", "rs.", "rs", "inr", "rupees", "rupee")
_RANGE_WORDS = ("to",)

_TRAILING = " \t\r\n.,;:!?-–—"
_NUMBER = re.compile(r"\d+(?:\.\d+)?")
_TOKEN = re.compile(r"\d+(?:\.\d+)?|[a-z]+")


def normalize_strict(text: str) -> str:
    """Case-fold, collapse whitespace runs, strip surrounding whitespace and trailing marks."""
    folded = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join(folded.split()).strip(_TRAILING)


def _strip_digit_commas(text: str) -> str:
    """45,00,000 -> 4500000, leaving a comma that separates words alone."""
    return re.sub(r"(?<=\d),(?=\d)", "", text)


def canonical_numbers(text: str) -> tuple[tuple[float, ...], tuple[str, ...]] | None:
    """Split a value into (numbers with magnitudes resolved, leftover words).

    Returns None when the value has no number in it, which is the signal to fall back to the
    strict comparison.

    A magnitude word that appears once applies to every number in the value, so "40-45 lakhs"
    reads as 40 lakh to 45 lakh rather than 40 to 4,500,000. A value that spells out its own
    magnitudes ("40 lakhs to 1 crore") gets each applied where it stands.
    """
    prepared = normalize_strict(text)
    for dash in _DASHES:
        prepared = prepared.replace(dash, "-")
    prepared = _strip_digit_commas(prepared)
    if not _NUMBER.search(prepared):
        return None

    tokens = _TOKEN.findall(prepared)
    numbers: list[list] = []          # [value, multiplier or None]
    leftover: list[str] = []
    magnitudes_seen: list[int] = []
    for token in tokens:
        if _NUMBER.fullmatch(token):
            numbers.append([float(token), None])
            continue
        multiplier = thresholds.MAGNITUDES.get(token)
        if multiplier is not None:
            magnitudes_seen.append(multiplier)
            if numbers and numbers[-1][1] is None:
                numbers[-1][1] = multiplier
            continue
        if token in _CURRENCY or token in _RANGE_WORDS:
            continue
        leftover.append(token)

    distinct = set(magnitudes_seen)
    if len(distinct) == 1:
        only = distinct.pop()
        for entry in numbers:
            if entry[1] is None:
                entry[1] = only

    resolved = tuple(value * (multiplier or 1) for value, multiplier in numbers)
    return resolved, tuple(sorted(leftover))


def normalize_number_aware(text: str) -> str:
    """A comparison key. Equal keys mean the two values agree under the secondary rule."""
    parsed = canonical_numbers(text)
    if parsed is None:
        return f"text:{normalize_strict(text)}"
    numbers, leftover = parsed
    rendered = "|".join(f"{value:.6g}" for value in numbers)
    return f"num:{rendered}|words:{' '.join(leftover)}"


#: Keyed by the names in thresholds.VALUE_NORMALIZATIONS so callers cannot invent a third.
NORMALIZERS = {
    thresholds.VALUE_NORMALIZATION_PRIMARY: normalize_strict,
    thresholds.VALUE_NORMALIZATION_SECONDARY: normalize_number_aware,
}


def agree(a: str, b: str, *, normalization: str) -> bool:
    try:
        normalizer = NORMALIZERS[normalization]
    except KeyError:
        raise ValueError(f"unknown normalization {normalization!r}") from None
    return normalizer(a) == normalizer(b)
