"""Value normalization tests. Every value here is invented.

The three cases Kapardhi named on 2026-10-02 are pinned explicitly, because they are the
specification for the secondary figure rather than examples of it.
"""

from __future__ import annotations

import pytest

import thresholds
import values

STRICT = thresholds.VALUE_NORMALIZATION_PRIMARY
NUMBER_AWARE = thresholds.VALUE_NORMALIZATION_SECONDARY


class TestTheThreeSpecifiedCases:
    """"40-45 lakhs", "40 to 45 lakhs" and "40-45 L" must be equal under number_aware."""

    SPECIFIED = ("40-45 lakhs", "40 to 45 lakhs", "40–45 L")

    @pytest.mark.parametrize("a", SPECIFIED)
    @pytest.mark.parametrize("b", SPECIFIED)
    def test_all_three_agree_under_number_aware(self, a, b):
        assert values.agree(a, b, normalization=NUMBER_AWARE)

    def test_but_strict_keeps_them_apart(self):
        assert not values.agree("40-45 lakhs", "40 to 45 lakhs", normalization=STRICT)
        assert not values.agree("40-45 lakhs", "40–45 L", normalization=STRICT)

    def test_the_en_dash_is_what_strict_cannot_see_past(self):
        assert values.normalize_strict("40–45 L") != values.normalize_strict("40-45 L")


class TestStrict:
    @pytest.mark.parametrize("a,b", [
        ("Flat", "flat"),
        ("  flat  ", "flat"),
        ("flat.", "flat"),
        ("3 BHK", "3   BHK"),
        ("villa,", "Villa"),
    ])
    def test_it_sees_past_case_space_and_trailing_marks(self, a, b):
        assert values.agree(a, b, normalization=STRICT)

    @pytest.mark.parametrize("a,b", [
        ("villa", "flat"),
        ("40 lakhs", "45 lakhs"),
        ("40 lakhs", "40 lakh"),
        ("3BHK", "3 BHK"),
    ])
    def test_and_nothing_else(self, a, b):
        assert not values.agree(a, b, normalization=STRICT)


class TestNumberAware:
    @pytest.mark.parametrize("a,b", [
        ("80 lakhs", "8000000"),
        ("₹45,00,000", "45 lakh"),
        ("45 lacs", "45 lakhs"),
        ("1 cr", "1 crore"),
        ("1 crore", "10000000"),
        ("40 lakhs to 1 crore", "40 lakh to 1 cr"),
        ("Rs 40 lakhs", "40 lakhs"),
        ("50k", "50 thousand"),
    ])
    def test_it_resolves_magnitudes_separators_and_currency(self, a, b):
        assert values.agree(a, b, normalization=NUMBER_AWARE)

    @pytest.mark.parametrize("a,b", [
        ("40 lakhs", "45 lakhs"),
        ("40 lakhs", "40"),
        ("40 lakhs", "40 crore"),
        ("40-45 lakhs", "40 lakhs"),
    ])
    def test_it_still_separates_different_quantities(self, a, b):
        assert not values.agree(a, b, normalization=NUMBER_AWARE)

    def test_an_approximation_is_part_of_the_value_not_noise(self):
        """Kapardhi's Q1 decision, 2026-10-02: "around 40 lakhs" is a VALUE of "~40 lakhs".

        So the two notations of that one value must agree, and neither may agree with the exact
        figure. Dropping the "~" as punctuation would make an approximation equal to an exact
        figure and flatter the annotators; keeping "around" as a leftover word would split one
        value into two.
        """
        assert values.agree("~40 lakhs", "around 40 lakhs", normalization=NUMBER_AWARE)
        assert values.agree("approximately 40 lakhs", "~40 lakhs", normalization=NUMBER_AWARE)
        assert values.agree("roughly 40 lakhs", "about 40 lakhs", normalization=NUMBER_AWARE)
        assert not values.agree("~40 lakhs", "40 lakhs", normalization=NUMBER_AWARE)
        assert not values.agree("around 40 lakhs", "40 lakhs", normalization=NUMBER_AWARE)

    def test_the_approximation_flag_survives_a_range(self):
        assert values.agree("~40-45 lakhs", "around 40 to 45 lakhs", normalization=NUMBER_AWARE)
        assert not values.agree("~40-45 lakhs", "40-45 lakhs", normalization=NUMBER_AWARE)

    def test_a_commitment_word_is_not_an_approximation_marker(self):
        """"maybe" changes the LABEL to HEDGED, not the value, so it is not collapsed here."""
        assert not values.agree("45", "maybe 45", normalization=NUMBER_AWARE)
        assert not values.agree("3BHK", "maybe 3BHK", normalization=NUMBER_AWARE)
        assert "maybe" not in thresholds.APPROXIMATION_MARKERS
        assert "might" not in thresholds.APPROXIMATION_MARKERS
        assert "probably" not in thresholds.APPROXIMATION_MARKERS

    def test_residual_words_are_compared_so_a_bare_number_match_is_not_enough(self):
        """The guard against "3BHK" and "3 bedroom" counting as the same value."""
        assert not values.agree("3BHK flat", "3 bedroom flat", normalization=NUMBER_AWARE)

    def test_a_trailing_magnitude_applies_to_every_number_in_a_range(self):
        numbers, _, _ = values.canonical_numbers("40-45 lakhs")
        assert numbers == (4_000_000.0, 4_500_000.0)

    def test_free_text_falls_back_to_the_strict_comparison(self):
        assert values.canonical_numbers("near the lake") is None
        assert values.agree("Near the Lake", "near the lake", normalization=NUMBER_AWARE)
        assert not values.agree("near the lake", "near the park", normalization=NUMBER_AWARE)


class TestRelationshipBetweenTheTwo:
    PAIRS = [
        ("40-45 lakhs", "40 to 45 lakhs"), ("flat", "flat"), ("villa", "flat"),
        ("80 lakhs", "8000000"), ("around 40", "40"), ("", ""), ("3BHK", "3 BHK"),
    ]

    def test_number_aware_never_disagrees_where_strict_agrees(self):
        """Strict is a lower bound, so the secondary figure can only ever be >= the primary."""
        for a, b in self.PAIRS:
            if values.agree(a, b, normalization=STRICT):
                assert values.agree(a, b, normalization=NUMBER_AWARE), (a, b)

    def test_an_unknown_normalization_is_an_error(self):
        with pytest.raises(ValueError, match="unknown normalization"):
            values.agree("a", "b", normalization="fuzzy")

    def test_only_the_two_pre_registered_normalizations_exist(self):
        assert set(values.NORMALIZERS) == set(thresholds.VALUE_NORMALIZATIONS)


class TestEdges:
    @pytest.mark.parametrize("text", ["", "   ", ".", None])
    def test_empty_and_missing_values_do_not_raise(self, text):
        assert isinstance(values.normalize_strict(text), str)
        assert isinstance(values.normalize_number_aware(text), str)

    def test_two_empty_values_agree_under_both_rules(self):
        assert values.agree("", "   ", normalization=STRICT)
        assert values.agree("", "   ", normalization=NUMBER_AWARE)

    def test_an_approximate_value_with_no_number_falls_back_to_strict(self):
        """"around Gachibowli" has no number, so there is nothing for the flag to attach to."""
        assert values.canonical_numbers("somewhere around Gachibowli") is None
        assert values.agree("around Gachibowli", "around gachibowli",
                            normalization=NUMBER_AWARE)
        assert not values.agree("around Gachibowli", "Gachibowli", normalization=NUMBER_AWARE)

    def test_a_decimal_survives(self):
        numbers, _, _ = values.canonical_numbers("1.5 crore")
        assert numbers == (15_000_000.0,)
