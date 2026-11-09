"""PE-001's measurements, A to G, and the Gate 1 verdict.

Pure functions over a list of `Item`. Nothing here reads a file, writes a file, calls a model or
touches the network, so every number below is reachable from a test with fabricated data.

Measurement letters match `docs/product/evals/PE-001-dataset-audit.md`, so a figure in
`metrics.json` can be traced to the record that pre-registered it.
"""

from __future__ import annotations

import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

from normalize import normalize_message, normalize_reply_template, stable_hash, word_count
from safety import class_names_safe_to_emit
from thresholds import (
    CHARS_PER_TOKEN_ESTIMATE,
    MAX_CLASS_CARDINALITY_SHARE,
    MAX_CLASS_NAME_CHARS,
    MAX_CLASS_NAME_WORDS,
    MAX_DISTINCT_CLASSES,
    MAX_CROSS_SPLIT_DUPLICATES,
    MAX_PILOT_OVERLAP,
    MIN_CLASS_N,
    MIN_MEMORY_DEPENDENT,
    REQUIRED_LABELER_COVERAGE,
    meets_floor,
)


@dataclass(frozen=True)
class Item:
    """One row of the labelling sheet: one user message and its labels."""

    row: int
    item_id: str
    conversation_id: str
    turn_index: int | None
    user_message: str
    action: str
    reply: str
    labeler: str
    split: str | None = None  # from a split-assignment file, when one exists


@dataclass
class Percentiles:
    mean: float
    median: float
    p90: float
    max: int
    min: int

    def as_dict(self) -> dict[str, float]:
        return {
            "mean": round(self.mean, 2),
            "median": round(self.median, 2),
            "p90": round(self.p90, 2),
            "max": self.max,
            "min": self.min,
        }


def _percentiles(values: list[int]) -> Percentiles:
    if not values:
        return Percentiles(0.0, 0.0, 0.0, 0, 0)
    ordered = sorted(values)
    # Nearest-rank p90. With n < 10 this is the maximum, which is the honest answer at that size
    # rather than an interpolation that implies precision the sample has not got.
    idx = max(0, min(len(ordered) - 1, int(round(0.9 * len(ordered))) - 1))
    return Percentiles(
        mean=statistics.fmean(ordered),
        median=statistics.median(ordered),
        p90=float(ordered[idx]),
        max=ordered[-1],
        min=ordered[0],
    )


# --- A. Corpus shape ------------------------------------------------------------------------------

def corpus_shape(items: list[Item]) -> dict[str, Any]:
    by_conv: dict[str, int] = Counter(i.conversation_id for i in items)
    labelled = [i for i in items if i.action.strip() and i.reply.strip()]
    sizes = sorted(by_conv.values())
    mean_cluster = statistics.fmean(sizes) if sizes else 0.0
    return {
        "rows": len(items),
        "conversations": len(by_conv),
        "distinct_user_messages_normalised": len({normalize_message(i.user_message) for i in items}),
        "labelled_items": len(labelled),
        "unlabelled_items": len(items) - len(labelled),
        "items_per_conversation": _percentiles(sizes).as_dict(),
        # The design effect for a cluster bootstrap is 1 + (mean_cluster_size - 1) * ICC. The ICC
        # needs per-item correctness, which only exists once PE-002 has run, so only the cluster
        # size is reported here and the plan's §3.2 intervals stay an upper bound on precision
        # until PE-002 supplies the other half.
        "mean_cluster_size": round(mean_cluster, 3),
        "design_effect": None,
        "design_effect_note_icc_from": "PE-001",
    }


# --- B. action class distribution -----------------------------------------------------------------

def action_distribution(items: list[Item]) -> dict[str, Any]:
    counts = Counter(i.action.strip() for i in items if i.action.strip())
    names = list(counts)
    withheld = not class_names_safe_to_emit(
        names,
        len(items),
        max_chars=MAX_CLASS_NAME_CHARS,
        max_words=MAX_CLASS_NAME_WORDS,
        max_distinct=MAX_DISTINCT_CLASSES,
        max_share=MAX_CLASS_CARDINALITY_SHARE,
    )
    keyed = {(stable_hash(n) if withheld else n): c for n, c in counts.items()}
    below = sorted(k for k, c in keyed.items() if not meets_floor(c, MIN_CLASS_N))
    total = sum(counts.values())
    return {
        "distinct_actions": len(counts),
        "class_names": "withheld_free_text_suspected" if withheld else "measurable",
        "counts": dict(sorted(keyed.items(), key=lambda kv: (-kv[1], kv[0]))),
        "classes_below_floor": below,
        "n_classes_below_floor": len(below),
        "majority_share": round(max(counts.values()) / total, 4) if total else 0.0,
    }


# --- C. reply templating --------------------------------------------------------------------------

def reply_templating(items: list[Item]) -> dict[str, Any]:
    replies = [i.reply for i in items if i.reply.strip()]
    n = len(replies)
    raw = len(set(replies))
    norm = len({normalize_reply_template(r) for r in replies})
    return {
        "replies_present": n,
        "distinct_replies_raw": raw,
        "distinct_replies_normalised": norm,
        # Low means templated. This is the number that decides whether `reply` is a second
        # classification (plan §3.4) or needs a metric chosen and paid for.
        "templating_ratio_raw": round(raw / n, 4) if n else None,
        "templating_ratio_normalised": round(norm / n, 4) if n else None,
        "reply_chars": _percentiles([len(r) for r in replies]).as_dict(),
        "reply_words": _percentiles([word_count(r) for r in replies]).as_dict(),
    }


# --- D. memory dependence, lower bound ------------------------------------------------------------

def memory_dependence(items: list[Item]) -> dict[str, Any]:
    """Count items whose normalised message appears elsewhere with a different gold action.

    **What this establishes, stated exactly:** that the gold `action` is **not a function of the
    normalised user message alone**. That is the useful fact, and it is narrower than "the action
    depends on prior turns".

    Two limits, both reported in the output rather than left to a reader:

    1. **A lower bound.** It sees only where a message repeats. A corpus of all-distinct messages
       scores 0 and may still be thoroughly context-dependent. So PE-001's condition 2 reads
       NOT_ESTABLISHED rather than FAIL on a shortfall, and the context-stripped re-label decides.
    2. **It conflates context dependence with label noise.** The same message carrying two
       different actions is consistent with the action depending on context, and equally consistent
       with the labels being inconsistent on identical inputs. *Found by Claude Code on 2026-11-09
       while smoke-testing this script on fabricated data, where the count saturated at every item
       because the fabricated actions were assigned at random.* Nothing here can separate the two;
       the re-label in D(2) is what does, which is a second reason that step is not optional.

    The `same_turn_index` / `different_turn_index` split below is a cheap discriminator rather than
    a decision: differing actions at the same position in a conversation are harder to explain by
    context than differing actions at different positions. It is reported, never thresholded.
    """
    groups: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        if it.action.strip():
            groups[normalize_message(it.user_message)].append(it)

    repeated = {k: v for k, v in groups.items() if len(v) >= 2}
    ambiguous = {k: v for k, v in repeated.items() if len({i.action.strip() for i in v}) >= 2}
    items_in_ambiguous = sum(len(v) for v in ambiguous.values())

    same_turn = 0
    for members in ambiguous.values():
        by_turn: dict[Any, set[str]] = defaultdict(set)
        for it in members:
            by_turn[it.turn_index].add(it.action.strip())
        if any(len(acts) >= 2 for acts in by_turn.values()):
            same_turn += 1

    return {
        "repeated_message_groups": len(repeated),
        "items_in_repeated_groups": sum(len(v) for v in repeated.values()),
        "ambiguous_message_groups": len(ambiguous),
        "items_in_ambiguous_groups": items_in_ambiguous,
        "is_lower_bound": True,
        "establishes": "action_not_a_function_of_message_alone",
        "conflates": "context_dependence_with_label_noise",
        # Diagnostic, not a verdict. A group where one position carries two different actions is
        # harder to explain by context than one where the positions differ.
        "ambiguous_groups_with_same_turn_conflict": same_turn,
        "ambiguous_groups_positions_differ_only": len(ambiguous) - same_turn,
        # Without repeated messages the measure has no denominator to work in, which is worth
        # seeing beside the result rather than inferring from it.
        "measure_has_purchase": len(repeated) > 0,
    }


# --- E. duplicates and pilot overlap --------------------------------------------------------------

def duplicates_and_overlap(
    items: list[Item],
    *,
    pilot_item_ids: set[str] | None,
    split_written: bool,
) -> dict[str, Any]:
    groups: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        groups[normalize_message(it.user_message)].append(it)
    dupes = {k: v for k, v in groups.items() if len(v) >= 2}

    cross_split: int | str
    if not split_written:
        cross_split = "split_not_yet_written"
    else:
        cross_split = sum(
            1 for v in dupes.values() if len({i.split for i in v if i.split}) >= 2
        )

    if pilot_item_ids is None:
        overlap: int | str = "manifest_not_supplied"
    else:
        overlap = sum(1 for it in items if it.item_id in pilot_item_ids)

    return {
        "duplicate_message_groups": len(dupes),
        "items_in_duplicate_groups": sum(len(v) for v in dupes.values()),
        # Group ids, not the text. Enough to find them in the sheet locally, and reversible by
        # nobody.
        "duplicate_group_ids": sorted(stable_hash(k) for k in dupes)[:50],
        "cross_split_duplicate_groups": cross_split,
        "exp000_pilot_overlap_items": overlap,
    }


# --- F. label completeness ------------------------------------------------------------------------

def completeness(items: list[Item]) -> dict[str, Any]:
    n = len(items)
    missing_labeler = sum(1 for i in items if not i.labeler.strip())
    return {
        "rows": n,
        "missing_conversation_id": sum(1 for i in items if not i.conversation_id.strip()),
        "missing_user_message": sum(1 for i in items if not i.user_message.strip()),
        "missing_action": sum(1 for i in items if not i.action.strip()),
        "missing_reply": sum(1 for i in items if not i.reply.strip()),
        "missing_labeler": missing_labeler,
        "labeler_coverage": round((n - missing_labeler) / n, 4) if n else 0.0,
    }


# --- G. prompt length ----------------------------------------------------------------------------

def prompt_lengths(items: list[Item]) -> dict[str, Any]:
    """Length of the context PE-002 would build: earlier turns of the conversation, then this one.

    Ordered by `turn_index` when the sheet has one, else by row order, which is the order the sheet
    was read in. The distinction matters and is recorded in `config.json`: without a turn index,
    "earlier in the conversation" is an assumption about the export's row order rather than a fact.
    """
    by_conv: dict[str, list[Item]] = defaultdict(list)
    for it in items:
        by_conv[it.conversation_id].append(it)

    chars: list[int] = []
    for conv in by_conv.values():
        ordered = sorted(
            conv, key=lambda i: (i.turn_index if i.turn_index is not None else i.row, i.row)
        )
        running = 0
        for it in ordered:
            running += len(it.user_message)
            chars.append(running)
            running += len(it.reply)

    est_tokens = [int(c / CHARS_PER_TOKEN_ESTIMATE) for c in chars]
    return {
        "prompt_chars": _percentiles(chars).as_dict(),
        "prompt_tokens_estimated": _percentiles(est_tokens).as_dict(),
        "token_figures_are": "estimate",
        "chars_per_token_divisor": CHARS_PER_TOKEN_ESTIMATE,
        "fits_32k_estimated": sum(1 for t in est_tokens if t <= 32_000),
        "fits_64k_estimated": sum(1 for t in est_tokens if t <= 64_000),
    }


def conversation_context(items: list[Item], target: Item) -> str:
    """The conversation up to and including `target`, as the original labelling saw it.

    Used by the label-noise re-test sheet, which must present an item under the SAME conditions the
    original labelling did. The memory-dependence sheet strips this on purpose; using one where the
    other belongs measures the wrong quantity, which is why they are separate functions and
    separate CLI flags.
    """
    same = [i for i in items if i.conversation_id == target.conversation_id]
    ordered = sorted(
        same, key=lambda i: (i.turn_index if i.turn_index is not None else i.row, i.row)
    )
    lines: list[str] = []
    for it in ordered:
        lines.append(f"customer: {it.user_message}")
        if it is target or (it.row == target.row and it.item_id == target.item_id):
            break
        if it.reply.strip():
            lines.append(f"bot: {it.reply}")
    return "\n".join(lines)


# --- Gate 1 ---------------------------------------------------------------------------------------

@dataclass
class Condition:
    name: str
    verdict: str
    observed: Any
    threshold: Any
    reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "verdict": self.verdict,
            "observed": self.observed,
            "threshold": self.threshold,
        }
        if self.reason:
            d["reason"] = self.reason
        return d


def gate_one(
    *,
    dist: dict[str, Any],
    memory: dict[str, Any],
    dupes: dict[str, Any],
    comp: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate PE-001's four pre-registered conditions. No condition is invented here."""
    conds: list[Condition] = []

    conds.append(
        Condition(
            "1_every_class_meets_floor",
            "PASS" if dist["n_classes_below_floor"] == 0 else "FAIL",
            dist["n_classes_below_floor"],
            MIN_CLASS_N,
            None if dist["n_classes_below_floor"] == 0 else "classes_below_floor_listed",
        )
    )

    n_mem = memory["items_in_ambiguous_groups"]
    if meets_floor(n_mem, MIN_MEMORY_DEPENDENT):
        conds.append(Condition("2_memory_dependent_items", "PASS", n_mem, MIN_MEMORY_DEPENDENT))
    else:
        # Pre-registered: a shortfall on a lower-bound measure is NOT_ESTABLISHED, not FAIL. The
        # context-stripped re-label sample decides it. PE-001's Metric, condition 2.
        conds.append(
            Condition(
                "2_memory_dependent_items",
                "NOT_ESTABLISHED",
                n_mem,
                MIN_MEMORY_DEPENDENT,
                "lower_bound_below_floor_recheck_decides",
            )
        )

    cross, overlap = dupes["cross_split_duplicate_groups"], dupes["exp000_pilot_overlap_items"]
    if isinstance(cross, str) or isinstance(overlap, str):
        conds.append(
            Condition(
                "3_no_cross_split_duplicates_or_pilot_overlap",
                "NOT_ESTABLISHED",
                {"cross_split": cross, "pilot_overlap": overlap},
                {"cross_split": MAX_CROSS_SPLIT_DUPLICATES, "pilot_overlap": MAX_PILOT_OVERLAP},
                "one_half_unchecked",
            )
        )
    else:
        ok = cross <= MAX_CROSS_SPLIT_DUPLICATES and overlap <= MAX_PILOT_OVERLAP
        conds.append(
            Condition(
                "3_no_cross_split_duplicates_or_pilot_overlap",
                "PASS" if ok else "FAIL",
                {"cross_split": cross, "pilot_overlap": overlap},
                {"cross_split": MAX_CROSS_SPLIT_DUPLICATES, "pilot_overlap": MAX_PILOT_OVERLAP},
            )
        )

    cov = comp["labeler_coverage"]
    conds.append(
        Condition(
            "4_labeler_coverage",
            "PASS" if cov >= REQUIRED_LABELER_COVERAGE else "FAIL",
            cov,
            REQUIRED_LABELER_COVERAGE,
        )
    )

    verdicts = [c.verdict for c in conds]
    if "FAIL" in verdicts:
        overall = "FAIL"
    elif "NOT_ESTABLISHED" in verdicts:
        overall = "NOT_ESTABLISHED"
    else:
        overall = "PASS"
    return {
        "overall": overall,
        "conditions": {c.name: c.as_dict() for c in conds},
    }
