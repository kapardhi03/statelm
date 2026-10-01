"""Tests for the statistical measures behind H1's agreement figures and H2's verdict.

The one-sided test's direction is asserted against synthetic data rather than assumed: getting
it backwards would silently invert H2's conclusion.
"""

from __future__ import annotations

import numpy as np
import pytest

import measures
import thresholds


class TestStrictlyDecreasing:
    @pytest.mark.parametrize(
        "values,expected",
        [
            ([0.9, 0.8, 0.7, 0.6, 0.5], True),
            ([0.9, 0.8, 0.8, 0.6, 0.5], False),  # a plateau is not decreasing
            ([0.9, 0.8, 0.7, 0.5, 0.6], False),  # one inversion
            ([0.5, 0.6], False),
            ([0.6, 0.5], True),
        ],
    )
    def test_cases(self, values, expected):
        assert measures.strictly_decreasing(values) is expected


class TestSpearmanAgainstIndex:
    def test_perfectly_decreasing_gives_minus_one(self):
        rho, _ = measures.spearman_against_index([0.9, 0.8, 0.7, 0.6, 0.5])
        assert rho == pytest.approx(-1.0)
        assert thresholds.spearman_meets_bound(rho)

    def test_one_adjacent_inversion_gives_exactly_minus_zero_point_nine(self):
        # This is what makes H2's inclusive <= -0.9 bound admit exactly one inversion.
        # n=5, a single adjacent transposition gives sum(d^2)=38, rho = 1 - 6*38/120 = -0.9.
        rho, _ = measures.spearman_against_index([0.9, 0.8, 0.7, 0.5, 0.6])
        assert rho == pytest.approx(-0.9)
        assert thresholds.spearman_meets_bound(rho)

    def test_that_case_is_below_the_bound_only_with_the_tolerance(self):
        # It computes as -0.8999999999999998, i.e. 2.2e-16 ABOVE -0.9, so a bare comparison
        # would reject the one case the rule explicitly admits. This pins the hazard.
        rho, _ = measures.spearman_against_index([0.9, 0.8, 0.7, 0.5, 0.6])
        assert rho > thresholds.H2_SPEARMAN_MAX
        assert thresholds.spearman_meets_bound(rho)

    def test_two_inversions_fall_outside_the_bound(self):
        rho, _ = measures.spearman_against_index([0.9, 0.7, 0.8, 0.5, 0.6])
        assert rho == pytest.approx(-0.8)
        assert not thresholds.spearman_meets_bound(rho)

    def test_the_tolerance_cannot_admit_anything_but_the_boundary_case(self):
        # Nine orders of magnitude below the 0.1 gap to the next configuration.
        assert thresholds.H2_SPEARMAN_TOLERANCE < 1e-6
        assert not thresholds.spearman_meets_bound(-0.89)

    def test_increasing_gives_plus_one(self):
        rho, _ = measures.spearman_against_index([0.5, 0.6, 0.7, 0.8, 0.9])
        assert rho == pytest.approx(1.0)

    def test_too_few_points_raises(self):
        with pytest.raises(ValueError, match="at least 3 points"):
            measures.spearman_against_index([0.9, 0.8])


class TestWilcoxonLower:
    def test_detects_x_below_y(self):
        rng = np.random.default_rng(0)
        y = rng.uniform(0.7, 0.9, size=60)
        x = y - 0.05
        _, p = measures.wilcoxon_lower(x, y)
        assert p < thresholds.H2_WILCOXON_ALPHA

    def test_does_not_fire_when_x_is_above_y(self):
        # The direction check: if the test were oriented the other way this would pass at 0.01
        # and H2 would be "supported" by data showing the opposite of its claim.
        rng = np.random.default_rng(1)
        y = rng.uniform(0.7, 0.9, size=60)
        x = y + 0.05
        _, p = measures.wilcoxon_lower(x, y)
        assert p > 0.5

    def test_identical_samples_give_no_evidence_instead_of_raising(self):
        values = [0.8] * 10
        stat, p = measures.wilcoxon_lower(values, values)
        assert (stat, p) == (0.0, 1.0)

    def test_paired_input_shapes_must_match(self):
        with pytest.raises(ValueError, match="paired input"):
            measures.wilcoxon_lower([0.1, 0.2], [0.1, 0.2, 0.3])

    def test_empty_sample_raises(self):
        with pytest.raises(ValueError, match="empty sample"):
            measures.wilcoxon_lower([], [])


class TestCohenKappa:
    def test_perfect_agreement_on_mixed_labels(self):
        assert measures.cohen_kappa([True, False, True, False], [True, False, True, False]) == 1.0

    def test_hand_computed_case(self):
        # observed 0.75; pa=0.75, pb=0.5 -> pe=0.5; kappa=(0.75-0.5)/0.5=0.5
        assert measures.cohen_kappa(
            [True, True, True, False], [True, True, False, False]
        ) == pytest.approx(0.5)

    def test_chance_level_agreement_is_zero(self):
        # observed 0.5; pa=pb=0.5 -> pe=0.5; kappa=0
        assert measures.cohen_kappa(
            [True, True, False, False], [True, False, True, False]
        ) == pytest.approx(0.0)

    def test_systematic_disagreement_is_negative(self):
        assert measures.cohen_kappa([True, True, False, False], [False, False, True, True]) < 0

    def test_both_constant_and_identical_is_one(self):
        assert measures.cohen_kappa([True] * 5, [True] * 5) == 1.0

    def test_both_constant_and_opposite_is_zero(self):
        assert measures.cohen_kappa([True] * 5, [False] * 5) == 0.0

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError, match="equal lengths"):
            measures.cohen_kappa([True], [True, False])

    def test_empty_raises(self):
        with pytest.raises(ValueError, match="empty sample"):
            measures.cohen_kappa([], [])
