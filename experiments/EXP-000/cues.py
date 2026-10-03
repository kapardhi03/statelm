"""Selection cues and target eligibility for the item sampler. Pure functions, no I/O.

These decide which turns get *sampled*, never what anything means. The distinction matters:
EXP-000's record forbids pre-labelling items or suggesting labels, so a cue match is recorded in
the manifest the researcher reads and never written into the sheet an annotator reads. An
annotator who could see "this turn matched a hedge cue" would be primed toward HEDGED.

Precision therefore does not need to be high. A false cue match costs a slightly less enriched
sample; it cannot corrupt a label.

**Eligibility is a different thing from enrichment, and getting them confused voided a run.**
A cue decides which of the *eligible* turns to prefer. Eligibility decides what can be a target
at all, and that is not a matter of preference: under the guideline's rule Q3 a seller turn
cannot establish a customer field, so a seller target yields NO-OP by construction and measures
nothing about agreement. Run 20261002T175103Z-f318529 sampled over every turn, drew 10 seller
turns out of 16, and produced 160 NO-OP labels and no kappa.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Sequence

import thresholds

#: Phrases that often accompany a speaker revising something they said earlier.
CORRECTION_CUES = (
    "actually", "sorry", "i meant", "i mean", "no wait", "scratch that", "instead",
    "correction", "my mistake", "rather than", "not that", "change that", "ignore that",
    "change",
    # Romanized Telugu and Hindi. Kapardhi's list of 2026-10-03, prompted by the v2 census:
    # 135 eligible customer turns produced 0 correction and 0 hedge matches against the
    # English-only lists, in a deployment where customers code-mix.
    "kaadu", "ledu ledu", "matlab", "nahi nahi",
)

#: Phrases that often accompany an underspecified or tentative value.
HEDGE_CUES = (
    "around", "approximately", "roughly", "maybe", "might", "perhaps", "or so", "ballpark",
    "up to", "at least", "somewhere", "thereabouts", "flexible", "depends", "not sure",
    "probably", "could be", "give or take", "around about",
    # Romanized Telugu and Hindi. Same provenance as the correction additions above.
    "konchem", "approx ga", "emo", "anukuntunna", "chuddam", "alochistanu", "telidu",
    "shayad", "lagbhag", "thoda", "dekhte hain", "pata nahi",
)

#: Cue words added on 2026-10-03 that are not English. Recorded separately so the census can
#: say how much of a stratum the code-mixed forms are responsible for: if they account for most
#: of it, the English-only lists were the problem; if they account for little, the phenomenon is
#: absent from the text channel and better cues will not recover it.
CODE_MIXED_CUES = (
    "kaadu", "ledu ledu", "matlab", "nahi nahi",
    "konchem", "approx ga", "emo", "anukuntunna", "chuddam", "alochistanu", "telidu",
    "shayad", "lagbhag", "thoda", "dekhte hain", "pata nahi",
)

#: Strata a target turn can belong to. "field_mention", "correction" and "hedge" carry quotas;
#: "multi_speaker" is reported for interest and has none; "plain" means no cue matched, and such
#: turns are drawn by the random remainder.
STRATA = ("field_mention", "correction", "hedge", "multi_speaker", "plain")

#: A turn counts as multi-speaker context when its window holds at least this many speakers.
MULTI_SPEAKER_MINIMUM = 3

#: A number next to a magnitude word: "80 lakhs", "1.2 cr", "50k". How a budget is usually said.
_AMOUNT = re.compile(
    r"\d[\d,.]*\s*(?:" + "|".join(re.escape(m) for m in sorted(thresholds.MAGNITUDES, key=len, reverse=True)) + r")(?!\w)",
    re.I)

#: A locality-shaped word: a stem of three or more letters ending in a common Indian suffix.
_LOCALITY = re.compile(
    r"(?<!\w)\w{3,}(?:" + "|".join(thresholds.LOCALITY_SUFFIXES) + r")(?!\w)", re.I)


@functools.lru_cache(maxsize=64)
def _matcher(cues: tuple[str, ...]) -> re.Pattern:
    return re.compile("|".join(rf"(?<!\w){re.escape(cue)}(?!\w)" for cue in cues), re.I)


@functools.lru_cache(maxsize=64)
def _field_matcher(cues: tuple[str, ...]) -> re.Pattern:
    """Like `_matcher`, but bounded by letters rather than word characters.

    "3BHK" is the commonest way a property type is written, and a word boundary will not match
    "bhk" there: the digit is a word character, so the lookbehind fails. Letter boundaries match
    it while still refusing "bhks" or "abhk".
    """
    return re.compile(
        "|".join(rf"(?<![a-z]){re.escape(cue)}(?![a-z])" for cue in cues), re.I)


_CORRECTION = _matcher(tuple(CORRECTION_CUES))
_HEDGE = _matcher(tuple(HEDGE_CUES))
_CODE_MIXED = _matcher(tuple(CODE_MIXED_CUES))


def has_correction_cue(text: str) -> bool:
    return bool(_CORRECTION.search(text or ""))


def has_hedge_cue(text: str) -> bool:
    return bool(_HEDGE.search(text or ""))


def distinct_speakers(rows: Sequence[dict]) -> int:
    return len({r.get("speaker_id") for r in rows if r.get("speaker_id")})


def has_code_mixed_cue(text: str) -> bool:
    """Whether a non-English cue matched. Counted in the census, never used as a stratum."""
    return bool(_CODE_MIXED.search(text or ""))


def role_of(turn: dict) -> str:
    return str(turn.get("speaker_role") or "").strip().lower()


def display_role(turn: dict) -> str:
    """What the annotator sees: "customer" or "seller".

    An unmapped role passes through unchanged rather than being coerced to one side, so a
    schema that grows a third party shows up in the sheet instead of being silently absorbed.
    """
    role = role_of(turn)
    return thresholds.ROLE_DISPLAY.get(role, role or "unknown")


def is_media_placeholder(text: str) -> bool:
    return (text or "").strip().lower().startswith(thresholds.MEDIA_PLACEHOLDER_PREFIX)


def word_count(text: str) -> int:
    return len((text or "").split())


def target_rejection(turn: dict) -> str | None:
    """Why this turn cannot be a target, or None if it can.

    Returns a reason rather than a bool so the sampler can report *why* a corpus yields few
    eligible turns. A run that finds almost nothing eligible is a fact about the corpus the
    researcher needs before any labelling, not after.
    """
    if role_of(turn) not in thresholds.TARGET_ROLES:
        return "not_customer"
    text = turn.get("text", "")
    if is_media_placeholder(text):
        return "media_placeholder"
    if not text.strip():
        return "empty"
    if word_count(text) < thresholds.MIN_TARGET_WORDS:
        return "too_short"
    return None


def is_eligible_target(turn: dict) -> bool:
    return target_rejection(turn) is None


def fields_mentioned(text: str, keywords: dict[str, Sequence[str]] | None = None) -> frozenset[str]:
    """Which pilot fields this text appears to mention. Sampling only, never a label.

    A budget is matched by an amount pattern as well as by its keywords, and a location by a
    locality-shaped word as well as by its indicator words, because neither is reliably a word
    from a fixed list.
    """
    keywords = thresholds.FIELD_KEYWORDS if keywords is None else keywords
    text = text or ""
    found = set()
    for field, words in keywords.items():
        if words and _field_matcher(tuple(words)).search(text):
            found.add(field)
    if _AMOUNT.search(text):
        found.add(thresholds.BUDGET_AMOUNT_FIELD)
    if _LOCALITY.search(text):
        found.add("location_preference")
    return frozenset(found & set(keywords))


def has_field_mention(text: str, keywords=None) -> bool:
    return bool(fields_mentioned(text, keywords))


def strata_for(turn: dict, context: Sequence[dict], *, keywords=None) -> frozenset[str]:
    """Which strata a turn belongs to. A turn can be in several, or only in "plain".

    **Every cue is matched against the target turn's own text**, never against the context. That
    was already true before run 20261002T175103Z-f318529 was voided; what made the cues select
    seller text was that seller turns were eligible targets at all, which they no longer are.
    A test pins the property so it stays true.

    "Multi-speaker turn" is read as a turn whose context window holds three or more distinct
    speakers, since a turn has exactly one speaker of its own. That is an interpretation of the
    experiment record's wording, not something the record states. It carries no quota.
    """
    found = set()
    text = turn.get("text", "")
    if has_field_mention(text, keywords):
        found.add("field_mention")
    if has_correction_cue(text):
        found.add("correction")
    if has_hedge_cue(text):
        found.add("hedge")
    if distinct_speakers([*context, turn]) >= MULTI_SPEAKER_MINIMUM:
        found.add("multi_speaker")
    return frozenset(found or {"plain"})


def per_cue_hits(texts: Sequence[str], cue_list: Sequence[str]) -> dict[str, int]:
    """How many of `texts` each cue matches, one entry per cue, zeros included.

    Built from the same `_matcher` the strata use, one cue at a time, so a diagnostic cannot
    report a match the sampler did not act on. **The zeros are the point.** A cue list whose
    every form scores zero has not been shown able to fire on the corpus at all, and a probe
    that never fires cannot separate an absent phenomenon from a probe that does not match the
    text. That is the question the v3 census left open.
    """
    patterns = {cue: _matcher((cue,)) for cue in cue_list}
    return {cue: sum(1 for text in texts if pattern.search(text or ""))
            for cue, pattern in patterns.items()}


def per_field_keyword_hits(texts: Sequence[str],
                           keywords: dict[str, Sequence[str]] | None = None
                           ) -> dict[str, dict[str, int]]:
    """`per_cue_hits` per field, letter-bounded as `fields_mentioned` matches keywords.

    The boundary difference is not cosmetic: a word boundary will not match "bhk" in "3BHK",
    so matching field keywords with `_matcher` would under-report what the sampler saw.
    """
    keywords = thresholds.FIELD_KEYWORDS if keywords is None else keywords
    out: dict[str, dict[str, int]] = {}
    for field, words in keywords.items():
        patterns = {word: _field_matcher((word,)) for word in words}
        out[field] = {word: sum(1 for text in texts if pattern.search(text or ""))
                      for word, pattern in patterns.items()}
    return out


def field_pattern_hits(texts: Sequence[str]) -> dict[str, int]:
    """The two matchers `fields_mentioned` uses besides the keyword lists.

    Without these the keyword counts are misleading: a budget mention is usually caught by the
    amount pattern ("80 lakhs"), not by the word "budget", so keyword hits of zero alongside a
    non-zero `field_mention` stratum is the expected shape rather than a contradiction.
    """
    return {
        "amount_pattern": sum(1 for text in texts if _AMOUNT.search(text or "")),
        "locality_suffix_pattern": sum(1 for text in texts if _LOCALITY.search(text or "")),
    }
