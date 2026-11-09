"""Each of PE-001's measurements, against fabricated data with known answers.

CLAUDE.md: "Write tests for anything that computes a metric or applies the ledger. A wrong metric
silently invalidates every experiment that uses it." These are those tests. Where a measurement is
a lower bound or a fallback, the test pins that behaviour too, because a lower bound silently read
as an estimate is the failure mode this audit is most exposed to.
"""

from __future__ import annotations

from conftest import item

from audit import (
    action_distribution,
    completeness,
    corpus_shape,
    duplicates_and_overlap,
    gate_one,
    memory_dependence,
    prompt_lengths,
    reply_templating,
)
from thresholds import MIN_CLASS_N, MIN_MEMORY_DEPENDENT


# --- A ---------------------------------------------------------------------------------------------

def test_corpus_shape_counts(simple_items):
    a = corpus_shape(simple_items)
    assert a["rows"] == 6
    assert a["conversations"] == 2
    assert a["labelled_items"] == 6
    assert a["unlabelled_items"] == 0
    assert a["distinct_user_messages_normalised"] == 5  # "same question" appears twice
    assert a["mean_cluster_size"] == 3.0


def test_corpus_shape_counts_unlabelled():
    items = [item(2, "c1", "a message", ""), item(3, "c1", "another", "a", reply="")]
    a = corpus_shape(items)
    assert a["labelled_items"] == 0
    assert a["unlabelled_items"] == 2


def test_design_effect_is_withheld_until_pe_002():
    """It needs an ICC, which needs per-item correctness, which PE-002 produces."""
    a = corpus_shape([item(2, "c1", "m", "a")])
    assert a["design_effect"] is None
    assert a["mean_cluster_size"] == 1.0


# --- B ---------------------------------------------------------------------------------------------

def test_action_distribution(simple_items):
    b = action_distribution(simple_items)
    assert b["distinct_actions"] == 3
    assert b["counts"] == {"a": 3, "b": 2, "c": 1}
    assert b["majority_share"] == round(3 / 6, 4)


def test_classes_below_the_floor_are_listed_not_dropped(simple_items):
    b = action_distribution(simple_items)
    # Every class here is under MIN_CLASS_N, so all three must be listed.
    assert b["n_classes_below_floor"] == 3
    assert sorted(b["classes_below_floor"]) == ["a", "b", "c"]
    assert sum(b["counts"].values()) == 6, "counts must survive the floor check"


def test_a_class_at_the_floor_is_not_below_it():
    items = [item(2 + n, "c1", f"m{n}", "a") for n in range(MIN_CLASS_N)]
    b = action_distribution(items)
    assert b["n_classes_below_floor"] == 0


def test_blank_actions_are_not_a_class():
    items = [item(2, "c1", "m", ""), item(3, "c1", "n", "a")]
    b = action_distribution(items)
    assert b["counts"] == {"a": 1}


# --- C ---------------------------------------------------------------------------------------------

def test_templated_replies_give_a_low_normalised_ratio():
    items = [
        item(2 + n, "c1", f"m{n}", "a", reply=f"Your visit is booked for {n} pm.")
        for n in range(10)
    ]
    c = reply_templating(items)
    assert c["distinct_replies_raw"] == 10
    # Digit runs collapse, so ten replies are one template.
    assert c["distinct_replies_normalised"] == 1
    assert c["templating_ratio_normalised"] == 0.1
    assert c["templating_ratio_raw"] == 1.0


def test_free_text_replies_give_a_high_normalised_ratio():
    items = [
        item(2, "c1", "m", "a", reply="thanks, I will check with my wife and revert"),
        item(3, "c1", "n", "a", reply="the carpet area is about nine hundred square feet"),
        item(4, "c1", "o", "a", reply="we can arrange a visit whenever suits you best"),
    ]
    c = reply_templating(items)
    assert c["templating_ratio_normalised"] == 1.0


def test_reply_templating_ignores_blank_replies():
    items = [item(2, "c1", "m", "a", reply=""), item(3, "c1", "n", "a", reply="ok")]
    c = reply_templating(items)
    assert c["replies_present"] == 1


def test_reply_lengths_reported():
    items = [item(2, "c1", "m", "a", reply="one two three")]
    c = reply_templating(items)
    assert c["reply_words"]["max"] == 3
    assert c["reply_chars"]["max"] == len("one two three")


# --- D ---------------------------------------------------------------------------------------------

def test_memory_dependence_lower_bound(simple_items):
    d = memory_dependence(simple_items)
    assert d["repeated_message_groups"] == 1
    assert d["items_in_repeated_groups"] == 2
    assert d["ambiguous_message_groups"] == 1
    assert d["items_in_ambiguous_groups"] == 2
    assert d["is_lower_bound"] is True
    assert d["measure_has_purchase"] is True


def test_measurement_d_states_what_it_establishes_and_what_it_conflates(simple_items):
    """The caveats travel in the output, so a reader cannot take the count for more than it is."""
    d = memory_dependence(simple_items)
    assert d["establishes"] == "action_not_a_function_of_message_alone"
    assert d["conflates"] == "context_dependence_with_label_noise"


def test_same_turn_conflict_is_separated_from_position_difference():
    """Two actions at the SAME position are harder to explain by context than at different ones."""
    same = [
        item(2, "c1", "same", "a", turn=1),
        item(3, "c2", "same", "b", turn=1),
    ]
    assert memory_dependence(same)["ambiguous_groups_with_same_turn_conflict"] == 1
    assert memory_dependence(same)["ambiguous_groups_positions_differ_only"] == 0

    differ = [
        item(2, "c1", "same", "a", turn=1),
        item(3, "c2", "same", "b", turn=4),
    ]
    assert memory_dependence(differ)["ambiguous_groups_with_same_turn_conflict"] == 0
    assert memory_dependence(differ)["ambiguous_groups_positions_differ_only"] == 1


def test_a_repeated_message_with_the_same_action_is_not_evidence():
    items = [item(2, "c1", "same", "a"), item(3, "c2", "same", "a")]
    d = memory_dependence(items)
    assert d["repeated_message_groups"] == 1
    assert d["ambiguous_message_groups"] == 0
    assert d["items_in_ambiguous_groups"] == 0


def test_an_all_distinct_corpus_scores_zero_and_says_the_measure_has_no_purchase():
    """The central caveat: 0 here does not mean the corpus is context-independent."""
    items = [item(2 + n, "c1", f"distinct message {n}", "a") for n in range(40)]
    d = memory_dependence(items)
    assert d["items_in_ambiguous_groups"] == 0
    assert d["repeated_message_groups"] == 0
    assert d["measure_has_purchase"] is False


def test_normalisation_is_applied_when_grouping_messages():
    items = [item(2, "c1", "Same Question!", "a"), item(3, "c2", "same   question", "b")]
    d = memory_dependence(items)
    assert d["ambiguous_message_groups"] == 1


def test_digits_do_not_collapse_when_grouping_messages():
    """Otherwise "budget is 40" and "budget is 50" would look like a repeat and inflate D."""
    items = [item(2, "c1", "budget is 40", "a"), item(3, "c2", "budget is 50", "b")]
    d = memory_dependence(items)
    assert d["ambiguous_message_groups"] == 0


# --- E ---------------------------------------------------------------------------------------------

def test_unsupplied_inputs_read_not_supplied_rather_than_zero(simple_items):
    e = duplicates_and_overlap(simple_items, pilot_item_ids=None, split_written=False)
    assert e["cross_split_duplicate_groups"] == "split_not_yet_written"
    assert e["exp000_pilot_overlap_items"] == "manifest_not_supplied"


def test_pilot_overlap_is_counted_when_the_manifest_is_supplied(simple_items):
    e = duplicates_and_overlap(simple_items, pilot_item_ids={"row-3", "row-9"}, split_written=False)
    assert e["exp000_pilot_overlap_items"] == 1


def test_cross_split_duplicates_are_counted_once_a_split_exists():
    items = [
        item(2, "c1", "same", "a", split="train"),
        item(3, "c2", "same", "a", split="test"),
        item(4, "c3", "other", "a", split="train"),
        item(5, "c4", "other", "a", split="train"),
    ]
    e = duplicates_and_overlap(items, pilot_item_ids=set(), split_written=True)
    assert e["duplicate_message_groups"] == 2
    assert e["cross_split_duplicate_groups"] == 1


def test_duplicate_group_ids_are_hashes_not_text(simple_items):
    e = duplicates_and_overlap(simple_items, pilot_item_ids=None, split_written=False)
    assert all(len(g) == 12 for g in e["duplicate_group_ids"])


# --- F ---------------------------------------------------------------------------------------------

def test_completeness_counts_each_missing_field():
    items = [
        item(2, "", "m", "a"),
        item(3, "c1", "", "a"),
        item(4, "c1", "m", ""),
        item(5, "c1", "m", "a", reply=""),
        item(6, "c1", "m", "a", labeler=""),
    ]
    f = completeness(items)
    assert f["missing_conversation_id"] == 1
    assert f["missing_user_message"] == 1
    assert f["missing_action"] == 1
    assert f["missing_reply"] == 1
    assert f["missing_labeler"] == 1
    assert f["labeler_coverage"] == 0.8


def test_full_labeler_coverage(simple_items):
    assert completeness(simple_items)["labeler_coverage"] == 1.0


# --- G ---------------------------------------------------------------------------------------------

def test_prompt_length_accumulates_over_a_conversation():
    items = [
        item(2, "c1", "aaaa", "a", reply="bb", turn=1),
        item(3, "c1", "cccc", "a", reply="dd", turn=2),
    ]
    g = prompt_lengths(items)
    # First prompt: 4 chars. Second: 4 + 2 (reply) + 4 = 10.
    assert g["prompt_chars"]["max"] == 10
    assert g["prompt_chars"]["min"] == 4


def test_turn_index_orders_the_conversation_not_row_order():
    items = [
        item(2, "c1", "second message", "a", reply="r", turn=2),
        item(3, "c1", "x", "a", reply="r", turn=1),
    ]
    g = prompt_lengths(items)
    assert g["prompt_chars"]["min"] == 1, "turn 1 is the single character, whatever its row"


def test_token_figures_are_labelled_as_estimates():
    g = prompt_lengths([item(2, "c1", "a" * 400, "a")])
    assert g["token_figures_are"] == "estimate"
    assert g["prompt_tokens_estimated"]["max"] == 100
    assert g["fits_32k_estimated"] == 1


# --- Gate 1 ----------------------------------------------------------------------------------------

def _gate(items, *, pilot=None, split=False):
    return gate_one(
        dist=action_distribution(items),
        memory=memory_dependence(items),
        dupes=duplicates_and_overlap(items, pilot_item_ids=pilot, split_written=split),
        comp=completeness(items),
    )


def _passing_items() -> list:
    """Enough items to clear every condition: one class of 40, 30+ ambiguous-group items."""
    items = [item(2 + n, f"c{n // 3}", f"unique message {n}", "a") for n in range(40)]
    # 16 repeated-message groups of 2, each with two different actions -> 32 ambiguous items.
    base = len(items) + 2
    for n in range(16):
        items.append(item(base + 2 * n, f"d{n}", f"repeat {n}", "a"))
        items.append(item(base + 2 * n + 1, f"e{n}", f"repeat {n}", "b"))
    return items


def test_gate_passes_when_every_condition_is_met():
    g = _gate(_passing_items(), pilot=set(), split=True)
    assert g["overall"] == "PASS"
    assert all(c["verdict"] == "PASS" for c in g["conditions"].values())


def test_gate_fails_on_a_class_below_the_floor(simple_items):
    g = _gate(simple_items, pilot=set(), split=True)
    assert g["conditions"]["1_every_class_meets_floor"]["verdict"] == "FAIL"
    assert g["overall"] == "FAIL"


def test_memory_shortfall_is_not_established_rather_than_failed():
    """Pre-registered: a lower-bound shortfall cannot refute condition 2."""
    items = [item(2 + n, "c1", f"unique {n}", "a") for n in range(MIN_CLASS_N)]
    g = _gate(items, pilot=set(), split=True)
    cond = g["conditions"]["2_memory_dependent_items"]
    assert cond["verdict"] == "NOT_ESTABLISHED"
    assert cond["threshold"] == MIN_MEMORY_DEPENDENT
    assert cond["reason"] == "lower_bound_below_floor_recheck_decides"
    assert g["overall"] == "NOT_ESTABLISHED"


def test_unchecked_inputs_make_condition_three_not_established():
    g = _gate(_passing_items(), pilot=None, split=False)
    assert g["conditions"]["3_no_cross_split_duplicates_or_pilot_overlap"]["verdict"] == "NOT_ESTABLISHED"
    assert g["overall"] == "NOT_ESTABLISHED"


def test_pilot_overlap_fails_the_gate():
    items = _passing_items()
    g = _gate(items, pilot={items[0].item_id}, split=True)
    assert g["conditions"]["3_no_cross_split_duplicates_or_pilot_overlap"]["verdict"] == "FAIL"


def test_missing_labeler_fails_condition_four():
    items = _passing_items()
    items.append(item(9000, "zz", "one more unique message", "a", labeler=""))
    g = _gate(items, pilot=set(), split=True)
    assert g["conditions"]["4_labeler_coverage"]["verdict"] == "FAIL"


def test_fail_outranks_not_established():
    """A FAIL anywhere must not be softened by a NOT_ESTABLISHED elsewhere."""
    g = _gate(simple_items_for_fail(), pilot=None, split=False)
    assert g["overall"] == "FAIL"


def simple_items_for_fail() -> list:
    return [item(2, "c1", "only message", "rare_class")]
