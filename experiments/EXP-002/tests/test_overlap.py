"""Tests for the overlap measures.

Every expected value here is computed by hand. A wrong overlap function does not produce
an obviously wrong answer, it produces a plausible wrong percentage that the gate would
then accept or reject for the wrong reason.
"""

from __future__ import annotations

import pytest

import overlap
import thresholds


class TestTokens:
    @pytest.mark.parametrize(
        "name,expected",
        [
            ("account_type", ("account", "type")),
            ("numberOfSeats", ("number", "of", "seats")),
            ("HouseNumber", ("house", "number")),
            ("has_live_music", ("has", "live", "music")),
            ("check-in-date", ("check", "in", "date")),
            ("price", ("price",)),
            ("", ()),
            ("__leading_and_trailing__", ("leading", "and", "trailing")),
            ("mixed_caseName_here", ("mixed", "case", "name", "here")),
            ("address2", ("address2",)),
        ],
    )
    def test_tokenization(self, name, expected):
        assert overlap.tokens(name) == expected


class TestSingularize:
    @pytest.mark.parametrize(
        "token,expected",
        [
            ("seats", "seat"),
            ("values", "value"),
            ("cities", "city"),
            ("classes", "class"),
            ("boxes", "box"),
            ("branches", "branch"),
            ("dishes", "dish"),
            ("address", "address"),
            ("status", "status"),
            ("analysis", "analysis"),
            ("has", "has"),
            ("was", "was"),
            ("this", "this"),
            ("does", "does"),
            ("gas", "gas"),
            ("price", "price"),
        ],
    )
    def test_rules_and_exceptions(self, token, expected):
        assert overlap.singularize(token) == expected

    def test_known_limitation_irregular_plurals(self):
        # Documented and accepted: N2 is secondary and decides nothing.
        assert overlap.singularize("children") == "children"


class TestPipelines:
    def test_n0_is_the_raw_string(self):
        assert overlap.n0("Check-In_dateTime") == "Check-In_dateTime"

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("account_type", "account type"),
            ("numberOfSeats", "number of seats"),
            ("HouseNumber", "house number"),
        ],
    )
    def test_n1(self, name, expected):
        assert overlap.n1(name) == expected

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("numberOfSeats", "number seat"),
            ("has_live_music", "has live music"),
            ("possible_values", "possible value"),
            ("price_of_the_ticket", "price ticket"),
        ],
    )
    def test_n2(self, name, expected):
        assert overlap.n2(name) == expected

    def test_n1_is_idempotent(self):
        once = overlap.n1("numberOfSeats")
        assert overlap.n1(once) == once

    def test_n2_can_empty_a_name_made_only_of_stopwords(self):
        # The run records any such name under names_normalizing_to_empty rather than
        # silently matching it against other empties.
        assert overlap.n2("the_of_a") == ""

    def test_unknown_pipeline_raises_rather_than_defaulting(self):
        with pytest.raises(ValueError, match="unknown normalization pipeline"):
            overlap.normalize("x", "N7")


class TestMatchFlagsAndRate:
    def test_flags_follow_query_order(self):
        flags = overlap.match_flags(["a", "zzz", "b"], ["b", "a"], pipeline="N0")
        assert flags == [True, False, True]

    def test_n0_is_case_sensitive_and_n1_is_not(self):
        assert overlap.match_flags(["Price"], ["price"], pipeline="N0") == [False]
        assert overlap.match_flags(["Price"], ["price"], pipeline="N1") == [True]

    def test_n1_matches_across_naming_styles(self):
        assert overlap.match_flags(["numberOfSeats"], ["number_of_seats"], pipeline="N1") == [True]

    def test_rate_is_a_percentage(self):
        assert overlap.rate_from_flags([True, True, False, False]) == 50.0
        assert overlap.rate_from_flags([True]) == 100.0
        assert overlap.rate_from_flags([False]) == 0.0

    def test_rate_over_empty_population_raises(self):
        with pytest.raises(ValueError, match="empty population"):
            overlap.rate_from_flags([])

    def test_duplicate_queries_count_once_each(self):
        # The primary unit is (service, slot) instances, so repeats must not collapse.
        flags = overlap.match_flags(["city", "city", "nope"], ["city"], pipeline="N0")
        assert flags == [True, True, False]
        assert overlap.rate_from_flags(flags) == pytest.approx(200 / 3)


class TestJaccard:
    def test_identical_sets(self):
        assert overlap.jaccard(["a", "b"], ["b", "a"]) == 1.0

    def test_disjoint_sets(self):
        assert overlap.jaccard(["a"], ["b"]) == 0.0

    def test_partial_overlap_by_hand(self):
        # {a,b,c} vs {b,c,d}: intersection 2, union 4
        assert overlap.jaccard(["a", "b", "c"], ["b", "c", "d"]) == 0.5

    def test_symmetry(self):
        a, b = ["a", "b", "c"], ["c", "d"]
        assert overlap.jaccard(a, b) == overlap.jaccard(b, a)

    def test_both_empty_is_zero_not_one(self):
        assert overlap.jaccard([], []) == 0.0

    def test_one_empty(self):
        assert overlap.jaccard(["a"], []) == 0.0

    def test_repeated_tokens_are_deduplicated(self):
        assert overlap.jaccard(["a", "a", "b"], ["a", "b"]) == 1.0

    def test_threshold_boundary_is_inclusive_at_the_documented_value(self):
        # {a,b,c,d} vs {a,b,e,f}: intersection 2, union 6 -> 1/3, below threshold.
        assert overlap.jaccard("abcd", "abef") < thresholds.JACCARD_THRESHOLD
        # {a,b,c} vs {b,c,d} -> exactly 0.5, which counts as clearing >= 0.5.
        assert overlap.jaccard(["a", "b", "c"], ["b", "c", "d"]) >= thresholds.JACCARD_THRESHOLD


class TestNearestByJaccard:
    def test_picks_the_highest_scoring_candidate(self):
        name, score = overlap.nearest_by_jaccard(
            "departure_city", ["arrival_city", "departure_city_name", "price"]
        )
        # departure_city_name: {departure,city} vs {departure,city,name} -> 2/3
        # arrival_city:        {departure,city} vs {arrival,city}        -> 1/3
        assert name == "departure_city_name"
        assert score == pytest.approx(2 / 3)

    def test_ties_break_on_sorted_order_not_input_order(self):
        forward = overlap.nearest_by_jaccard("city", ["b_city", "a_city"])
        reverse = overlap.nearest_by_jaccard("city", ["a_city", "b_city"])
        assert forward == reverse == ("a_city", pytest.approx(0.5))

    def test_empty_candidates(self):
        assert overlap.nearest_by_jaccard("city", []) == (None, 0.0)


class TestBands:
    @pytest.mark.parametrize("value,expected", [(59.9, False), (60.0, True), (65.0, True), (70.0, True), (70.1, False)])
    def test_slot_band_is_inclusive(self, value, expected):
        assert thresholds.in_band(value, thresholds.GATE_SLOT_BAND) is expected

    @pytest.mark.parametrize("value,expected", [(65.9, False), (66.0, True), (76.0, True), (76.1, False)])
    def test_intent_band_is_inclusive(self, value, expected):
        assert thresholds.in_band(value, thresholds.GATE_INTENT_BAND) is expected

    def test_pre_registered_values_are_the_ones_in_the_experiment_record(self):
        # Guards against an accidental edit to a pre-registered threshold.
        assert thresholds.GATE_SLOT_BAND == (60.0, 70.0)
        assert thresholds.GATE_INTENT_BAND == (66.0, 76.0)
        assert thresholds.COSINE_THRESHOLD == 0.8
        assert thresholds.JACCARD_THRESHOLD == 0.5
        assert thresholds.H1_MIN_RATE == 50.0
        assert thresholds.H2_C1_MAX_EXACT_RATE == 70.0
        assert thresholds.H2_C2_MIN_RETAINED == 80.0
