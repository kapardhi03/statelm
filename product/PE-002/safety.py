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
        "no_label_noise_ceiling",
        "stage_2",
        "B0",
        "B1",
        "B2",
        "B3",
        "B4",
        "B5",
        "B-triv",
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
        "prompt_b1_sha256",
        "prompt_sha256",
        "providers_sha256",
        "consent_sha256",
        "consent_instructed_on",
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

# Values that come from the configuration files Kapardhi writes — a model id, a backend name, a
# provider name, an effort level, a short-hash list. Not derived from client data, but not a closed
# set either: a model id cannot be enumerated in advance. Bounded by a conservative charset and a
# length instead, which is enough to keep a sentence out.
CONFIG_IDENTIFIER_KEYS: frozenset[str] = frozenset(
    {
        "model",
        "backend",
        "provider",
        "provider_ref",
        "prompt_file",
        "effort",
        "step",
        "stage",
        "split",
        "unsupported_settings",
        "rungs_run",
        "fewshot_item_id_hashes",
        "columns_mapped",
    }
)
_CONFIG_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_./:+"
)
MAX_CONFIG_IDENTIFIER_CHARS = 128

# One field is short prose rather than an identifier: the price table's provenance, which he writes
# so a cost figure can be checked later. Length-bounded and newline-free; its value is his
# configuration text, never anything read from the corpus.
CONFIG_TEXT_KEYS: frozenset[str] = frozenset({"price_table_version"})
MAX_CONFIG_TEXT_CHARS = 200

# Subtrees whose every string, however deeply nested, is configuration rather than data: the rung
# -> provider map, the model table, what each backend actually sent. Enumerating their inner keys
# would mean editing this file whenever a backend gains a setting, which is how a guard rots; the
# charset bound travels down instead.
CONFIG_IDENTIFIER_SUBTREE_KEYS: frozenset[str] = frozenset(
    {
        "rung_to_provider",
        "provider_models",
        "settings_sent",
        "rung_meta",
        "consent_providers",
        "lexical_settings",
    }
)

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
        if key in CONFIG_IDENTIFIER_KEYS or key in CONFIG_IDENTIFIER_SUBTREE_KEYS:
            if (
                not obj
                or len(obj) > MAX_CONFIG_IDENTIFIER_CHARS
                or not set(obj) <= _CONFIG_ID_CHARS
            ):
                _fail(path, obj, "config identifier is empty, too long, or outside its charset")
            return
        if key in CONFIG_TEXT_KEYS:
            if not obj or len(obj) > MAX_CONFIG_TEXT_CHARS or any(c in obj for c in "\r\n"):
                _fail(path, obj, "config text is empty, too long, or contains a line break")
            return
        if key in CLASS_LABEL_KEYS:
            if not obj or len(obj) > MAX_CLASS_LABEL_CHARS or any(c in obj for c in "\r\n\t"):
                _fail(path, obj, "class label is empty, too long, or contains a line break")
            return
        if obj not in ALLOWED_VALUE_STRINGS:
            _fail(path, obj, "string value is not in the controlled vocabulary")
        return
    if isinstance(obj, dict):
        inherited = key if key in CONFIG_IDENTIFIER_SUBTREE_KEYS else None
        for k, v in obj.items():
            if not isinstance(k, str):
                _fail(f"{path}.{k!r}", k, "dict key is not a string")
            assert_output_safe(v, f"{path}.{k}", key=inherited or k)
        return
    if isinstance(obj, (list, tuple)):
        inherited = key if key in CONFIG_IDENTIFIER_SUBTREE_KEYS else key
        for i, v in enumerate(obj):
            assert_output_safe(v, f"{path}[{i}]", key=inherited)
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
