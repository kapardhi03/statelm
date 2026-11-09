"""The privacy guard on PE-001's output.

`.claude/rules/data-privacy.md`: client conversation text never leaves Kapardhi's machine, and the
tools that touch it return aggregates only. This audit reads the user messages and the replies,
because its keyword-adjacent measurements cannot be computed without them, so the guarantee has to
be enforced at the boundary rather than hoped for: every value in `metrics.json` is checked before
it is written.

The mechanism is a type-and-shape check, not a scan for anything that looks like a sentence. A
scan would pass anything it failed to recognise, which is the wrong way round. Here, a value is
allowed only if it is a number, a bool, null, or a string drawn from a controlled set; a string
that is not on the allowlist fails the write, whatever it contains.
"""

from __future__ import annotations

import re
from typing import Any

# Strings that may appear as *values* in metrics.json. Verdicts, reasons, identifiers and the
# controlled vocabulary of the report. Anything else must be a number, a bool or null.
ALLOWED_VALUE_STRINGS: frozenset[str] = frozenset(
    {
        "PASS",
        "FAIL",
        "NOT_ESTABLISHED",
        "not_measurable",
        "measurable",
        "withheld_free_text_suspected",
        "split_not_yet_written",
        # Gate 1 reason codes. A closed set on purpose: if reasons were free-form prose, the guard
        # would have to admit arbitrary strings, and then it would stop being a guard. Their
        # meanings are spelled out in README.md.
        "classes_below_floor_listed",
        # What measurement D does and does not establish, carried in the output itself so a reader
        # cannot take the count for more than it is.
        "action_not_a_function_of_message_alone",
        "context_dependence_with_label_noise",
        "lower_bound_below_floor_recheck_decides",
        "one_half_unchecked",
        "manifest_not_supplied",
        "estimate",
        "PE-001",
        # --- PE-002's additions ---
        "PE-002",
        "stage_1",
        "make_split",
        "train",
        "dev",
        "test",
        "B-triv-maj",
        "B-triv-lex",
        "no_prompted_rung_yet",
        "scikit_learn_not_installed",
        "degenerate_single_class_train",
        # config.json's record of how turns were ordered.
        "turn_index",
        "export_row_order",
        # The logical field names config.json lists under columns_mapped. Ours, not the sheet's:
        # the sheet's header names are configuration and are deliberately NOT emitted.
        "conversation_id",
        "user_message",
        "action",
        "reply",
        "labeler",
        "item_id",
    }
)

# Keys whose string value is a caller-supplied identifier rather than data: a run id, a git commit,
# a hash, a schema version. Checked against a strict charset instead of the allowlist.
IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {
        "run_id",
        "git_commit",
        "input_sha256",
        "script_version",
        "experiment",
        "generated_at",
        "columns_sha256",
        "split_assignment_sha256",
        # Short non-reversible group ids, from normalize.stable_hash.
        "duplicate_group_ids",
    }
)

# Keys whose string values are labels from the `action` taxonomy, or hashes standing in for them.
# These are Kapardhi's class names, not client content, and emitting them is how PE-001 answers
# Q18. They are bounded rather than enumerated, because the taxonomy is not known to this
# repository until the audit runs. Upstream, `looks_like_free_text` has already replaced them with
# hashes if the column looks like free text, so the bound here is a second line and not the first.
CLASS_LABEL_KEYS: frozenset[str] = frozenset({"classes_below_floor", "floor_class"})
MAX_CLASS_LABEL_CHARS = 64

_IDENTIFIER_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.:+TZ")


class OutputSafetyError(AssertionError):
    """Raised when a value that is not provably an aggregate reaches the output."""


def _fail(path: str, value: Any, why: str) -> None:
    # The offending value is NOT included in the message: this error can be printed to a terminal
    # or a log, and a guard that leaks the thing it caught is not a guard.
    raise OutputSafetyError(
        f"{path}: {why} (value of type {type(value).__name__} withheld from this message)"
    )


def assert_output_safe(obj: Any, path: str = "$", *, key: str | None = None) -> None:
    """Walk a would-be metrics.json and raise unless every value is provably an aggregate.

    Dict keys may be arbitrary strings: a key is a label from the action taxonomy or a group id,
    both of which the caller has already decided to emit. Values are what this guards.
    """
    if obj is None or isinstance(obj, (int, float, bool)):
        return
    if isinstance(obj, str):
        if key in IDENTIFIER_KEYS:
            if not obj or not set(obj) <= _IDENTIFIER_CHARS:
                _fail(path, obj, "identifier contains characters outside the strict charset")
            return
        if key in CLASS_LABEL_KEYS:
            if not obj or len(obj) > MAX_CLASS_LABEL_CHARS or any(c in obj for c in "\r\n\t"):
                _fail(path, obj, "class label is empty, too long, or contains a line break")
            return
        if obj not in ALLOWED_VALUE_STRINGS:
            _fail(path, obj, "string value is not in the controlled vocabulary")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                _fail(f"{path}.{k!r}", k, "dict key is not a string")
            assert_output_safe(v, f"{path}.{k}", key=k)
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            assert_output_safe(v, f"{path}[{i}]", key=key)
        return
    _fail(path, obj, "value is not a number, bool, null, controlled string, dict or list")


# A class label looks like a label: letters, digits, spaces and the separators people use in a
# taxonomy. No sentence punctuation, no line breaks, nothing exotic.
_CLASS_LABEL_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z _.\-/]*$")


def class_names_safe_to_emit(
    values: list[str],
    n_items: int,
    *,
    max_chars: int,
    max_words: int,
    max_distinct: int,
    max_share: float,
) -> bool:
    """Whether the `action` column's values may be emitted as names rather than hashes.

    PE-001 emits the action taxonomy on purpose: it is the answer to Q18 and the class distribution
    is unreadable without it. An annotation label is Kapardhi's own vocabulary, not conversation
    text, so emitting it is not what `data-privacy.md` forbids.

    The risk this guards is different: if the column turned out to hold free-form notes rather than
    a closed set, those notes could quote a customer. So the test is a **positive pattern** — every
    value must look like a label — rather than a hunt for things that look like prose. A negative
    heuristic passes whatever it fails to recognise, which is the wrong way round, and an earlier
    version of this function was exactly that: it let a 37-character single-word value through, and
    `test_no_sentinel_reaches_metrics` caught it.

    All five conditions must hold. Any failure sends the whole column to hashes, counts unaffected.
    """
    if not values or n_items <= 0:
        return False
    if len(values) > max_distinct:
        return False
    if (len(values) / n_items) > max_share:
        return False
    for v in values:
        if not v or len(v) > max_chars:
            return False
        if len(v.split()) > max_words:
            return False
        if not _CLASS_LABEL_PATTERN.match(v):
            return False
    return True
