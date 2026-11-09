"""Text normalisers used by PE-001's measurements.

These run on client text, on Kapardhi's machine, and nothing they return is written to
`metrics.json`: they exist so that counts of *groups* can be computed. Keeping them in one module
means the templating ratio, the memory-dependence lower bound and the duplicate check all group
text the same way, which is the only way those three numbers can be read against each other.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")
_DIGIT_RUN = re.compile(r"\d+")
# Keep letters, digits and spaces. Dropping punctuation is deliberate: "ok!" and "ok" are the same
# message for the purpose of asking whether a message repeats.
_NON_ALNUM = re.compile(r"[^\w\s]", re.UNICODE)


def normalize_message(text: str) -> str:
    """Normalise a user message for grouping: NFKC, casefold, strip punctuation, collapse spaces.

    Digits are kept. "budget is 40" and "budget is 50" are different messages, and collapsing them
    would inflate the memory-dependence lower bound by making distinct messages look repeated.
    """
    s = unicodedata.normalize("NFKC", text or "").casefold()
    s = _NON_ALNUM.sub(" ", s)
    return _WHITESPACE.sub(" ", s).strip()


def normalize_reply_template(text: str) -> str:
    """Normalise a reply for *template* grouping: as above, and digit runs become a slot marker.

    Digits are collapsed here and not in `normalize_message`, because the question is the opposite
    one: whether two replies are the same template with different values filled in. "visit at 4pm"
    and "visit at 6pm" are one template; treating them as two would hide that the replies are
    templated and send us into §3.4's expensive metric choices for nothing.
    """
    s = unicodedata.normalize("NFKC", text or "").casefold()
    s = _NON_ALNUM.sub(" ", s)
    s = _DIGIT_RUN.sub("#", s)
    return _WHITESPACE.sub(" ", s).strip()


def stable_hash(text: str) -> str:
    """A short, stable, non-reversible id for a piece of text.

    Used where a group has to be identified in the output without the text itself appearing: the
    duplicate-cluster list and, if the `action` column turns out to hold free text, the class
    labels. Truncated to 12 hex characters, which is ample for naming a few hundred groups and
    carries no information about the content beyond equality.
    """
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:12]


def word_count(text: str) -> int:
    s = _WHITESPACE.sub(" ", (text or "").strip())
    return 0 if not s else len(s.split(" "))
