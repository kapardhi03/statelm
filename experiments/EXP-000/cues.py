"""Selection cues for the item sampler. Pure functions, no I/O.

These decide which turns get *sampled*, never what anything means. The distinction matters:
EXP-000's record forbids pre-labelling items or suggesting labels, so a cue match is recorded in
the manifest the researcher reads and never written into the sheet an annotator reads. An
annotator who could see "this turn matched a hedge cue" would be primed toward HEDGED.

Precision therefore does not need to be high. A false cue match costs a slightly less enriched
sample; it cannot corrupt a label.
"""

from __future__ import annotations

import re
from collections.abc import Sequence

#: Phrases that often accompany a speaker revising something they said earlier.
CORRECTION_CUES = (
    "actually", "sorry", "i meant", "i mean", "no wait", "scratch that", "instead",
    "correction", "my mistake", "rather than", "not that", "change that", "ignore that",
)

#: Phrases that often accompany an underspecified or tentative value.
HEDGE_CUES = (
    "around", "approximately", "roughly", "maybe", "might", "perhaps", "or so", "ballpark",
    "up to", "at least", "somewhere", "thereabouts", "flexible", "depends", "not sure",
    "probably", "could be", "give or take",
)

STRATA = ("correction", "hedge", "multi_speaker", "plain")

#: A turn counts as multi-speaker context when its window holds at least this many speakers.
MULTI_SPEAKER_MINIMUM = 3


def _matcher(cues: Sequence[str]) -> re.Pattern:
    return re.compile("|".join(rf"(?<!\w){re.escape(cue)}(?!\w)" for cue in cues), re.I)


_CORRECTION = _matcher(CORRECTION_CUES)
_HEDGE = _matcher(HEDGE_CUES)


def has_correction_cue(text: str) -> bool:
    return bool(_CORRECTION.search(text or ""))


def has_hedge_cue(text: str) -> bool:
    return bool(_HEDGE.search(text or ""))


def distinct_speakers(rows: Sequence[dict]) -> int:
    return len({r.get("speaker_id") for r in rows if r.get("speaker_id")})


def strata_for(turn: dict, context: Sequence[dict]) -> frozenset[str]:
    """Which strata a turn belongs to. A turn can be in several, or only in "plain".

    "Multi-speaker turn" is read as a turn whose context window holds three or more distinct
    speakers, since a turn has exactly one speaker of its own. That is an interpretation of the
    experiment record's wording, not something the record states.
    """
    found = set()
    text = turn.get("text", "")
    if has_correction_cue(text):
        found.add("correction")
    if has_hedge_cue(text):
        found.add("hedge")
    if distinct_speakers([*context, turn]) >= MULTI_SPEAKER_MINIMUM:
        found.add("multi_speaker")
    return frozenset(found or {"plain"})
