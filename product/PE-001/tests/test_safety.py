"""The privacy guarantee, asserted rather than trusted.

`.claude/rules/data-privacy.md` requires that only aggregates leave the machine this audit runs on.
These tests are the mechanism check: fabricated items carry a sentinel in every free-text field,
and the sentinel must reach neither output file nor the printed summary. A negative control makes
sure the search could fail.
"""

from __future__ import annotations

import json

import pytest
from conftest import SENTINEL

from audit import action_distribution
from run_audit import build_metrics, summarise
from safety import OutputSafetyError, assert_output_safe, class_names_safe_to_emit


def test_no_sentinel_reaches_metrics(sentinel_items):
    metrics = build_metrics(sentinel_items, pilot_ids=None, split_written=False)
    blob = json.dumps(metrics)
    assert SENTINEL not in blob


def test_no_sentinel_reaches_the_printed_summary(sentinel_items):
    metrics = build_metrics(sentinel_items, pilot_ids=None, split_written=False)
    assert SENTINEL not in summarise(metrics)


def test_the_sentinel_search_can_fail(sentinel_items):
    """Negative control: if the sentinel were emitted, the tests above would catch it."""
    assert SENTINEL in sentinel_items[0].user_message
    assert SENTINEL in json.dumps({"leaked": sentinel_items[0].reply})


def test_metrics_pass_the_output_guard(simple_items):
    metrics = build_metrics(simple_items, pilot_ids=None, split_written=False)
    assert_output_safe(metrics, "$metrics")  # must not raise


def test_guard_rejects_free_text_value():
    with pytest.raises(OutputSafetyError):
        assert_output_safe({"note": "the customer said he would call back"})


def test_guard_rejects_a_bad_identifier():
    with pytest.raises(OutputSafetyError):
        assert_output_safe({"git_commit": "not a commit! spaces and punctuation"})


def test_guard_accepts_a_good_identifier():
    assert_output_safe({"git_commit": "ab65ca4", "generated_at": "2026-11-08T23:59:00Z"})


def test_guard_rejects_an_overlong_class_label():
    with pytest.raises(OutputSafetyError):
        assert_output_safe({"classes_below_floor": ["x" * 65]})


def test_guard_accepts_a_plausible_class_label():
    assert_output_safe({"classes_below_floor": ["ask_budget", "schedule site visit"]})


def test_guard_rejects_an_unknown_type():
    with pytest.raises(OutputSafetyError):
        assert_output_safe({"when": object()})


def test_guard_walks_into_lists_and_dicts():
    with pytest.raises(OutputSafetyError):
        assert_output_safe({"a": [{"b": {"c": "free text that is not allowed"}}]})


def test_error_message_does_not_repeat_the_offending_value():
    """A guard that prints what it caught is not a guard."""
    with pytest.raises(OutputSafetyError) as exc:
        assert_output_safe({"note": SENTINEL})
    assert SENTINEL not in str(exc.value)


# --- the class-label guard on the `action` column --------------------------------------------------
# A POSITIVE pattern: every value must look like a label. An earlier version asked instead whether
# a value looked like prose, and let a 37-character single-word value through; the sentinel test
# above is what caught it. These cases pin the five conditions.

GUARD = dict(max_chars=40, max_words=6, max_distinct=50, max_share=0.5)


def test_guard_admits_a_plain_taxonomy():
    assert class_names_safe_to_emit(["ask_budget", "schedule site visit", "no-op"], 100, **GUARD)


def test_guard_refuses_an_overlong_value():
    assert not class_names_safe_to_emit(["x" * 41], 100, **GUARD)


def test_guard_refuses_a_wordy_value():
    assert not class_names_safe_to_emit(["one two three four five six seven"], 100, **GUARD)


def test_guard_refuses_sentence_punctuation():
    assert not class_names_safe_to_emit(["asked about price, so replied."], 100, **GUARD)


def test_guard_refuses_too_many_distinct_values():
    assert not class_names_safe_to_emit([f"a{i}" for i in range(51)], 1000, **GUARD)


def test_guard_refuses_a_high_cardinality_share():
    assert not class_names_safe_to_emit([f"a{i}" for i in range(30)], 40, **GUARD)


def test_guard_refuses_an_empty_value():
    assert not class_names_safe_to_emit(["ok", ""], 100, **GUARD)


def test_guard_refuses_empty_input():
    assert not class_names_safe_to_emit([], 0, **GUARD)


def test_class_names_are_withheld_when_the_column_holds_notes(sentence_action_items):
    """The case the guard exists for: a note about a conversation can quote the customer."""
    dist = action_distribution(sentence_action_items)
    assert dist["class_names"] == "withheld_free_text_suspected"
    assert SENTINEL not in json.dumps(dist)
    assert all(len(k) == 12 for k in dist["counts"])


def test_a_withheld_column_still_reports_its_counts(sentence_action_items):
    """Withholding names must not cost us the distribution."""
    dist = action_distribution(sentence_action_items)
    assert sum(dist["counts"].values()) == len(sentence_action_items)


def test_metrics_stay_clean_when_the_action_column_holds_notes(sentence_action_items):
    metrics = build_metrics(sentence_action_items, pilot_ids=None, split_written=False)
    assert SENTINEL not in json.dumps(metrics)
    assert_output_safe(metrics, "$metrics")


def test_class_names_are_emitted_for_a_closed_set(simple_items):
    dist = action_distribution(simple_items)
    assert dist["class_names"] == "measurable"
    assert set(dist["counts"]) == {"a", "b", "c"}
