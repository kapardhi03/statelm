"""Corpus diagnostics for EXP-000: can the cue lists fire on this text at all?

Prompted by the v3 census of 2026-10-03. Kapardhi's 16 romanized Telugu and Hindi forms matched
0 of 135 eligible customer turns -- and so did the 33 English forms that were already in the
lists: "around", "maybe", "up to", "at least", "flexible", "depends", "probably", "actually",
"sorry", "change". A probe whose every form scores zero has not been shown capable of firing,
and cannot separate "the phenomenon is absent from the text channel" from "the probe does not
match this text", or from the text not being what the pipeline is assumed to deliver.

Two measurements tell those apart, and this module computes both:

1. **Which forms ever match.** Per-cue and per-keyword counts, zeros included. If the English
   cues fire at an ordinary rate and only the romanized ones are silent, cue language is not
   the explanation. If nothing fires, the instrument is the finding rather than the corpus.
2. **What script the text is written in.** An ASCII-only probe cannot match Telugu or
   Devanagari script, however well chosen its words are. "thoda" does not match the Devanagari
   spelling of the same word, and no addition to a romanized list will change that.

**Counts only.** Every string this module can put in a record is a cue, a field name, a keyword
or a script label, all of which are already in this repository. No turn text, no excerpt, no
conversation id and no speaker id passes through, and a test pins that over the written file.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

import cues
import thresholds

#: Unicode blocks named in the diagnostic. Telugu and Devanagari because this deployment's
#: customers write in them; anything else non-ASCII is counted but not identified, since
#: naming a block Claude has no reason to expect would be guesswork.
TELUGU_BLOCK = (0x0C00, 0x0C7F)
DEVANAGARI_BLOCK = (0x0900, 0x097F)

#: `telugu`, `devanagari` and `other_non_ascii` are "contains", so one text can be in several.
#: `ascii_only` is exclusive of all three. Shares are of the texts measured, not of each other.
SCRIPT_BUCKETS = ("telugu", "devanagari", "other_non_ascii", "ascii_only")

#: Where a field's keyword list came from. The distinction decides whether the keywords
#: may be named in a tracked record: the built-in lists are repository content already,
#: and a `--field-keywords` file is not.
KEYWORD_SOURCE_BUILT_IN = "built_in"
KEYWORD_SOURCE_FILE = "field_keywords_file"

NO_CUE_NOTE = ("Every form in both cue lists scored zero on these texts. A probe that never "
               "fires cannot separate an absent phenomenon from a probe that does not match "
               "the text, so this count does not support either reading on its own.")


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _in_block(code: int, block: tuple[int, int]) -> bool:
    return block[0] <= code <= block[1]


def scripts_of(text: str) -> frozenset[str]:
    """Which script buckets a single text falls in. Empty text counts as ASCII-only."""
    found = set()
    for char in text or "":
        code = ord(char)
        if code < 128:
            continue
        if _in_block(code, TELUGU_BLOCK):
            found.add("telugu")
        elif _in_block(code, DEVANAGARI_BLOCK):
            found.add("devanagari")
        else:
            found.add("other_non_ascii")
    return frozenset(found or {"ascii_only"})


def has_non_ascii_letter(text: str) -> bool:
    """Whether any *letter* is outside ASCII, which is a different question from any character.

    A rupee sign, an emoji or a curly quote puts a turn outside ASCII without putting a single
    word out of an ASCII cue list's reach: "budget is around Rs.80 lakhs" written with U+20B9
    still matches the hedge cue "around". In a WhatsApp property corpus that is the common case,
    not a corner one, so counting it as unmatchable would overstate the diagnostic's central
    finding in the direction that flatters it.
    """
    return any(ord(char) > 127 and char.isalpha() for char in text or "")


def script_profile(texts: Sequence[str]) -> dict:
    """Counts and shares per script bucket.

    `shares` is None when there is nothing to measure. An empty corpus has no composition, and
    reporting 0.0 would read as "no Telugu" rather than "nothing was measured" -- the same
    reason `kappa.cohen_kappa` returns None rather than 0.0 when it is undefined.
    """
    counts = {bucket: 0 for bucket in SCRIPT_BUCKETS}
    for text in texts:
        for bucket in scripts_of(text):
            counts[bucket] += 1
    total = len(texts)
    shares = ({bucket: round(count / total, 4) for bucket, count in counts.items()}
              if total else None)
    other = [text for text in texts if "other_non_ascii" in scripts_of(text)]
    return {
        "texts": total,
        "counts": counts,
        "shares": shares,
        #: Texts holding at least one non-ASCII letter, in any block. This, not the sum of the
        #: non-ASCII buckets, is the number that bears on whether an ASCII cue list can reach
        #: the words in a text.
        "with_non_ascii_letters": sum(1 for text in texts if has_non_ascii_letter(text)),
        #: Splits the `other_non_ascii` bucket, whose members are mostly symbols in practice.
        "other_non_ascii_detail": {
            "with_non_ascii_letter": sum(1 for text in other if has_non_ascii_letter(text)),
            "symbols_only": sum(1 for text in other if not has_non_ascii_letter(text)),
        },
    }


def keyword_hits_for_record(texts: Sequence[str], keywords=None) -> dict:
    """Per-keyword counts, naming a keyword only when it is this repository's own.

    `--field-keywords` lets the researcher supply locality names from a file he may keep out of
    the repository, and `load_field_keywords` promises no name from it reaches runs/. This
    record is tracked by git, so naming them would break that promise for the sake of a
    slightly more readable file. An overridden field reports its counts in the order of the
    file it came from and names nothing; the researcher reads them against his own file, and
    the repository learns only how many forms there were and how often each fired.

    This protects a list kept outside the repository and nothing more. The committed
    `field_keywords.yaml` is already public, and counts in its order are readable against it.

    A field counts as overridden when its effective list differs from the built-in one, which
    is exact: `load_field_keywords` replaces a field's list wholesale or leaves it alone.
    """
    keyword_map = thresholds.FIELD_KEYWORDS if keywords is None else keywords
    per_keyword = cues.per_field_keyword_hits(texts, keyword_map)
    out: dict[str, dict] = {}
    for field, hits in per_keyword.items():
        built_in = thresholds.FIELD_KEYWORDS.get(field)
        if built_in is not None and tuple(keyword_map[field]) == tuple(built_in):
            out[field] = {"source": KEYWORD_SOURCE_BUILT_IN, "hits": hits}
        else:
            out[field] = {
                "source": KEYWORD_SOURCE_FILE,
                "forms": len(hits),
                "hits_in_file_order": [hits[word] for word in keyword_map[field]],
            }
    return out


def cue_diagnostics(texts: Sequence[str], *, keywords=None) -> dict:
    """The whole diagnostic over one set of texts, which are the eligible targets.

    `keywords` is the effective field-keyword mapping, so a run with `--field-keywords` is
    diagnosed against the lists it actually used rather than the built-in ones.
    """
    keyword_map = keywords if keywords is not None else None
    per_cue = {
        "correction": cues.per_cue_hits(texts, cues.CORRECTION_CUES),
        "hedge": cues.per_cue_hits(texts, cues.HEDGE_CUES),
    }
    field_keywords = keyword_hits_for_record(texts, keyword_map)
    no_cue_matched = not any(count for counts in per_cue.values() for count in counts.values())
    field_mentioning = [text for text in texts if cues.has_field_mention(text, keyword_map)]
    report = {
        "eligible_targets": len(texts),
        "cues": per_cue,
        "cue_forms_that_matched": {
            name: sorted(cue for cue, count in counts.items() if count)
            for name, counts in per_cue.items()
        },
        "code_mixed_forms": sorted(cues.CODE_MIXED_CUES),
        "no_cue_matched": no_cue_matched,
        "field_keywords": field_keywords,
        "field_patterns": cues.field_pattern_hits(texts),
        "script": {
            "eligible_targets": script_profile(texts),
            "field_mentioning_targets": script_profile(field_mentioning),
            "cue_strings": script_profile(sorted({*cues.CORRECTION_CUES, *cues.HEDGE_CUES})),
            "field_keyword_strings": script_profile(
                sorted({word for words in (keyword_map or thresholds.FIELD_KEYWORDS).values()
                        for word in words})),
        },
    }
    if no_cue_matched:
        report["note"] = NO_CUE_NOTE
    return report


#: The population the word-floor block measures, named so the no-text test can allow it by
#: constant rather than by a copy of the string.
FLOOR_POPULATION = "customer text turns rejected as too_short"

FLOOR_NOTE = ("Counts only, and no threshold. Whether this many short-but-substantive turns "
              "is too many for the word floor to stand is Kapardhi's call, not a number this "
              "tool decides.")


def short_turn_diagnostics(texts: Sequence[str], *, keywords=None) -> dict:
    """What the word floor throws away, over the customer text turns it excludes.

    `MIN_TARGET_WORDS` is 3, and it was pre-registered to keep the sampler off the 2-to-16
    character turns that helped void run 20261002T175103Z-f318529. But the floor cannot tell a
    content-free turn from a short answer that settles a field: "50 lakhs", "3 BHK" and
    "maybe 60" are all one or two words and all substantive. If the excluded turns carry field
    mentions and cues at a serious rate, the floor is part of why the corpus reads state-sparse,
    which is neither of the two readings the v3 census left open.

    Per field and per pattern rather than per keyword, so a `--field-keywords` list kept off
    this machine is not named here either.
    """
    keyword_map = thresholds.FIELD_KEYWORDS if keywords is None else keywords
    per_cue = {
        "correction": cues.per_cue_hits(texts, cues.CORRECTION_CUES),
        "hedge": cues.per_cue_hits(texts, cues.HEDGE_CUES),
    }
    field_mentions = {field: 0 for field in keyword_map}
    with_field, with_cue = 0, 0
    word_counts = {count: 0 for count in range(1, thresholds.MIN_TARGET_WORDS)}
    for text in texts:
        fields = cues.fields_mentioned(text, keyword_map)
        for field in fields:
            field_mentions[field] += 1
        cued = cues.has_hedge_cue(text) or cues.has_correction_cue(text)
        with_field += bool(fields)
        with_cue += bool(cued)
        words = cues.word_count(text)
        word_counts[words] = word_counts.get(words, 0) + 1
    return {
        "population": FLOOR_POPULATION,
        "min_target_words": thresholds.MIN_TARGET_WORDS,
        "turns": len(texts),
        "word_counts": word_counts,
        "field_mentions": field_mentions,
        "field_patterns": cues.field_pattern_hits(texts),
        "cues": per_cue,
        "cue_forms_that_matched": {
            name: sorted(cue for cue, count in counts.items() if count)
            for name, counts in per_cue.items()
        },
        "with_field_mention": with_field,
        "with_hedge_or_correction_cue": with_cue,
        "note": FLOOR_NOTE,
    }


def report_short_turns(block: dict, *, out) -> None:
    """The excluded population, printed as its own block so it is not read as the sample."""
    floor = block["min_target_words"]
    counts = ", ".join(f"{_plural(words, 'word')} {count}"
                       for words, count in sorted(block["word_counts"].items()))
    print(f"--- customer text turns excluded by the {floor}-word floor ---", file=out)
    print(f"excluded turns: {block['turns']} ({counts})", file=out)
    print(f"with a field mention: {block['with_field_mention']} "
          f"{ {k: v for k, v in block['field_mentions'].items() if v} }", file=out)
    print(f"field keyword patterns: {block['field_patterns']}", file=out)
    for name, cue_counts in block["cues"].items():
        matched = block["cue_forms_that_matched"][name]
        print(f"{name} cues: {len(matched)} of {len(cue_counts)} forms matched anything "
              f"({_plural(sum(cue_counts.values()), 'hit')})", file=out)
        if matched:
            print(f"  matched: {', '.join(matched)}", file=out)
    print(f"with a hedge or correction cue: {block['with_hedge_or_correction_cue']}", file=out)
    print(f"note: {FLOOR_NOTE}", file=out)
    print(file=out)


def report_diagnostics(diagnostics: dict, *, out) -> None:
    """The headline on the terminal. The file holds every count; this holds the finding."""
    script = diagnostics["script"]["eligible_targets"]
    shares = script["shares"] or {}
    print(f"eligible targets measured: {diagnostics['eligible_targets']}", file=out)
    for name, counts in diagnostics["cues"].items():
        matched = diagnostics["cue_forms_that_matched"][name]
        print(f"{name} cues: {len(matched)} of {len(counts)} forms matched anything "
              f"({_plural(sum(counts.values()), 'hit')})", file=out)
        if matched:
            print(f"  matched: {', '.join(matched)}", file=out)
    print(f"field keyword patterns: {diagnostics['field_patterns']}", file=out)
    print("script mix of eligible targets: "
          + ", ".join(f"{bucket} {script['counts'][bucket]}"
                      + (f" ({shares[bucket]:.0%})" if shares else "")
                      for bucket in SCRIPT_BUCKETS), file=out)
    if diagnostics["no_cue_matched"]:
        print(f"WARNING: {NO_CUE_NOTE}", file=out)
    #: Letters, not characters. A turn is only out of an ASCII cue list's reach for the words
    #: written in another script; a rupee sign or an emoji puts nothing out of reach.
    with_letters = script["with_non_ascii_letters"]
    if with_letters and diagnostics["no_cue_matched"]:
        print(f"WARNING: {with_letters} eligible target(s) contain words written in a "
              "non-ASCII script. No form in these ASCII cue lists can match those words, so a "
              "hedge or correction expressed in them is invisible here however many romanized "
              "words are added. Any ASCII words in the same turn remain matchable.", file=out)
    symbols = script["other_non_ascii_detail"]["symbols_only"]
    if symbols:
        print(f"note: a further {symbols} target(s) are non-ASCII by symbol only (a currency "
              "sign, an emoji). Their words are ASCII and the cue lists can match them.",
              file=out)
    print(file=out)


def probe_fingerprint(keywords=None) -> dict:
    """A digest of the exact cue and keyword lists a run measured with.

    The git commit in `config.json` already covers this when the working tree is clean. It is
    not clean while someone is editing a cue list, which is exactly the moment a count gets
    taken and later misfiled against the wrong version of the probe.
    """
    keyword_map = thresholds.FIELD_KEYWORDS if keywords is None else keywords
    parts = [
        ("correction", sorted(cues.CORRECTION_CUES)),
        ("hedge", sorted(cues.HEDGE_CUES)),
        *((f"field:{field}", sorted(words)) for field, words in sorted(keyword_map.items())),
    ]
    rolling = hashlib.sha256()
    for name, items in parts:
        rolling.update(f"{name}:{'|'.join(items)}\n".encode("utf-8"))
    return {
        "sha256": rolling.hexdigest(),
        "correction_forms": len(cues.CORRECTION_CUES),
        "hedge_forms": len(cues.HEDGE_CUES),
        "code_mixed_forms": len(cues.CODE_MIXED_CUES),
        "field_keyword_forms": {field: len(words)
                                for field, words in sorted(keyword_map.items())},
    }
