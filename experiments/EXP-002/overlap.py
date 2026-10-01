"""Name normalization pipelines and overlap measures for EXP-002.

Pure functions, no I/O, no dataset knowledge. Every function here feeds a reported number,
so each one is covered by `tests/test_overlap.py`.

Normalization pipelines (fixed in the experiment record):
  N0  raw string, exactly as it appears in the schema. The gate and both hypotheses use N0.
  N1  lowercase + split snake_case / camelCase / hyphens into tokens, joined by one space.
  N2  N1 + singularize + drop stopwords. Secondary only.

N2 is deliberately lossy and rule-based. Its limits are documented on `singularize` and
pinned by tests. No abbreviation expansion exists in any pipeline.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence

NORMALIZATION_VERSION = "1"

_SPLIT_CHARS = re.compile(r"[_\-\s]+")
_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")

#: Dropped by N2 only, after singularization.
STOPWORDS = frozenset(
    {"the", "a", "an", "of", "for", "to", "in", "on", "at", "by", "with", "and", "or", "is", "be"}
)

#: Words `singularize` must leave alone. Without these, the generic trailing-"s" rule turns
#: "has" into "ha" and "this" into "thi".
NEVER_SINGULARIZED = frozenset(
    {"this", "has", "was", "its", "does", "goes", "news", "plus", "series", "species",
     "always", "sometimes"}
)


def tokens(name: str) -> tuple[str, ...]:
    """Split a schema name into lowercase tokens. This is the N1 tokenization."""
    spaced = _CAMEL_BOUNDARY.sub(" ", name)
    return tuple(part.lower() for part in _SPLIT_CHARS.split(spaced) if part)


def singularize(token: str) -> str:
    """Conservative rule-based singularization, used by N2 only.

    Leaves alone: anything in NEVER_SINGULARIZED, tokens of 3 characters or fewer, and
    tokens ending in "ss", "us" or "is" ("address", "status", "analysis"). Otherwise
    "-ies" becomes "-y", "-ses/-xes/-zes/-ches/-shes" lose "es", and a trailing "s" is
    dropped. It is wrong on irregular plurals ("children", "people") by design: N2 never
    decides anything, and a plural-stemming library would be a dependency for a secondary
    number.
    """
    if token in NEVER_SINGULARIZED or len(token) <= 3:
        return token
    if token.endswith(("ss", "us", "is")):
        return token
    if token.endswith("ies") and len(token) > 4:
        return token[:-3] + "y"
    for suffix in ("ses", "xes", "zes", "ches", "shes"):
        if token.endswith(suffix):
            return token[:-2]
    if token.endswith("s"):
        return token[:-1]
    return token


def n0(name: str) -> str:
    """Raw string, unchanged. The gate's pipeline."""
    return name


def n1(name: str) -> str:
    return " ".join(tokens(name))


def n2(name: str) -> str:
    return " ".join(t for t in (singularize(t) for t in tokens(name)) if t not in STOPWORDS)


PIPELINES = {"N0": n0, "N1": n1, "N2": n2}


def normalize(name: str, pipeline: str) -> str:
    """Apply a named pipeline. Raises on an unknown pipeline rather than defaulting."""
    try:
        return PIPELINES[pipeline](name)
    except KeyError:
        raise ValueError(f"unknown normalization pipeline {pipeline!r}; have {sorted(PIPELINES)}")


def normalized_set(names: Iterable[str], pipeline: str) -> set[str]:
    return {normalize(name, pipeline) for name in names}


def match_flags(
    query_names: Sequence[str], reference_names: Iterable[str], *, pipeline: str
) -> list[bool]:
    """Per-query exact-match flags against the reference set, under one pipeline.

    Returned in query order, so a caller can line the flags up with its own records and
    report which names matched. Rates are derived from these flags, never counted
    separately, so the headline number and the evidence list cannot drift apart.
    """
    reference = normalized_set(reference_names, pipeline)
    return [normalize(name, pipeline) in reference for name in query_names]


def rate_from_flags(flags: Sequence[bool]) -> float:
    """Percentage of True flags.

    Raises on an empty sequence: a gate silently reporting 0.0% over an empty population
    would look like a refutation instead of a bug.
    """
    if not flags:
        raise ValueError("cannot compute a rate over an empty population")
    return 100.0 * sum(flags) / len(flags)


def jaccard(a: Iterable[str], b: Iterable[str]) -> float:
    """Token Jaccard. Two empty token sets score 0.0, not 1.0, by convention."""
    sa, sb = set(a), set(b)
    union = sa | sb
    if not union:
        return 0.0
    return len(sa & sb) / len(union)


def nearest_by_jaccard(name: str, candidates: Sequence[str]) -> tuple[str | None, float]:
    """Highest-Jaccard candidate for `name`, by N1 tokens.

    Ties break on the candidate's sorted order, so the result does not depend on input
    ordering. Returns (None, 0.0) for an empty candidate list.
    """
    best_name: str | None = None
    best_score = -1.0
    query = tokens(name)
    for candidate in sorted(candidates):
        score = jaccard(query, tokens(candidate))
        if score > best_score:
            best_name, best_score = candidate, score
    if best_name is None:
        return None, 0.0
    return best_name, best_score
