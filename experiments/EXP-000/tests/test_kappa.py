"""Arithmetic tests for kappa.py, on tables small enough to check by hand.

Every expected value here is derived on paper in the test's own comment rather than taken from
a previous run of this code, which would only prove the code agrees with itself.
"""

from __future__ import annotations

import pytest

import kappa
import thresholds


def table(both_x: int, a_x_b_y: int, a_y_b_x: int, both_y: int):
    """A 2x2 agreement table as a list of label pairs."""
    return ([("X", "X")] * both_x + [("X", "Y")] * a_x_b_y
            + [("Y", "X")] * a_y_b_x + [("Y", "Y")] * both_y)


class TestCohenKappa:
    def test_perfect_agreement_is_exactly_one(self):
        # 3 X/X and 2 Y/Y: po = 1, pe = (3/5)(3/5) + (2/5)(2/5) = 0.52,
        # kappa = (1 - 0.52) / (1 - 0.52) = 1.
        assert kappa.cohen_kappa(table(3, 0, 0, 2)) == 1.0

    def test_chance_level_is_exactly_zero(self):
        # 1 in each cell: po = 0.5. Both marginals are 2/2, so pe = 0.25 + 0.25 = 0.5.
        # kappa = (0.5 - 0.5) / 0.5 = 0.
        assert kappa.cohen_kappa(table(1, 1, 1, 1)) == 0.0

    def test_a_hand_worked_middling_case(self):
        # 4 X/X, 4 Y/Y, one disagreement each way: po = 0.8, marginals 5/5 both ways so
        # pe = 0.5, kappa = 0.3 / 0.5 = 0.6.
        assert kappa.cohen_kappa(table(4, 1, 1, 4)) == pytest.approx(0.6)

    def test_systematic_disagreement_is_negative(self):
        # Raters invert each other: po = 0, pe = 0.5, kappa = -1.
        assert kappa.cohen_kappa(table(0, 5, 5, 0)) == -1.0

    def test_a_single_label_gives_undefined_not_one(self):
        """Both raters said the same single thing about everything.

        Expected agreement is 1, so there is no variance for chance correction to act on.
        Returning 1.0 would read as perfect agreement and 0.0 as chance; the honest answer is
        that kappa has no value here.
        """
        assert kappa.cohen_kappa([("NO-OP", "NO-OP")] * 20) is None

    def test_empty_input_is_undefined(self):
        assert kappa.cohen_kappa([]) is None

    def test_percent_agreement_is_not_kappa(self):
        pairs = table(1, 1, 1, 1)
        assert kappa.percent_agreement(pairs) == 0.5
        assert kappa.cohen_kappa(pairs) == 0.0


class TestThresholdBoundary:
    """The float hazard that made meets_threshold() necessary.

    This is the reason the comparison is not a bare `kappa >= 0.6`. The table is small enough
    to occur in EXP-000: 18 items with a category used twice by one rater and twice by the
    other is an ordinary rare-abstention shape.
    """

    def test_an_exact_three_fifths_computes_just_below(self):
        value = kappa.cohen_kappa(table(2, 1, 1, 14))
        # On paper: po = 16/18, marginals 3/18 and 3/18 in-category,
        # pe = (3/18)(3/18) + (15/18)(15/18) = 234/324 = 13/18;
        # kappa = (16/18 - 13/18) / (1 - 13/18) = (3/18) / (5/18) = 3/5.
        assert value == 0.5999999999999996
        assert value < 0.6, "if this ever passes, the hazard is gone and the tolerance can go"

    def test_the_tolerance_admits_it(self):
        assert thresholds.meets_threshold(kappa.cohen_kappa(table(2, 1, 1, 14))) is True

    def test_the_tolerance_does_not_admit_a_genuinely_low_kappa(self):
        assert thresholds.meets_threshold(0.59) is False
        assert thresholds.meets_threshold(0.5999) is False

    def test_undefined_in_undefined_out(self):
        assert thresholds.meets_threshold(None) is None


class TestOneVsRest:
    def test_it_collapses_everything_else(self):
        pairs = [("A", "A"), ("A", "A"), ("B", "C"), ("C", "B"), ("B", "B")]
        # For label A: both-in 2, both-out 3, no disagreement -> perfect.
        assert kappa.one_vs_rest_kappa(pairs, "A") == 1.0
        # B and C disagree with each other but both are "out" of A, so A is unaffected.

    def test_a_category_nobody_used_is_undefined(self):
        pairs = [("A", "A")] * 4 + [("B", "B")] * 4
        assert kappa.one_vs_rest_kappa(pairs, "HEDGED") is None

    def test_counts_distinguish_either_from_both(self):
        pairs = [("A", "A"), ("A", "B"), ("B", "A"), ("B", "B")]
        assert kappa.category_counts(pairs, "A") == {
            "n_rater_a": 2, "n_rater_b": 2, "n_either": 3, "n_both": 1}


class TestConfusionMatrix:
    def test_rows_are_rater_a_and_margins_add_up(self):
        labels = ("X", "Y")
        pairs = table(4, 1, 2, 3)
        counts = kappa.confusion_matrix(pairs, labels)
        assert counts == [[4, 1], [2, 3]]
        assert [sum(row) for row in counts] == [5, 5]            # rater A's totals
        assert [sum(col) for col in zip(*counts)] == [6, 4]      # rater B's totals
        assert sum(sum(row) for row in counts) == len(pairs)

    def test_every_vocabulary_label_gets_a_row_even_unused(self):
        counts = kappa.confusion_matrix([("NO-OP", "NO-OP")], thresholds.LABELS)
        assert len(counts) == len(thresholds.LABELS)
        assert sum(sum(row) for row in counts) == 1


class TestPercentile:
    def test_against_a_hand_checkable_series(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        assert kappa._percentile(values, 0.0) == 1.0
        assert kappa._percentile(values, 0.5) == 3.0
        assert kappa._percentile(values, 1.0) == 5.0
        # 0.25 of the way along four gaps is index 1.0 exactly.
        assert kappa._percentile(values, 0.25) == 2.0

    def test_it_interpolates_between_neighbours(self):
        assert kappa._percentile([0.0, 10.0], 0.5) == 5.0

    def test_a_single_value_is_its_own_percentile(self):
        assert kappa._percentile([7.0], 0.025) == 7.0


class TestBootstrap:
    def build(self, conversations: int, per_conversation: int):
        """Conversations that disagree at *different* rates.

        The heterogeneity is the point. If every conversation held the same pattern, resampling
        conversations with replacement would draw the same multiset of pairs every time and the
        cluster interval would collapse to a single point with zero width. Between-cluster
        variance is what a cluster bootstrap measures, so a fixture without any measures nothing.
        """
        pairs, clusters = [], []
        for c in range(conversations):
            disagreements = c % (per_conversation // 2 + 1)
            for i in range(per_conversation):
                if i < disagreements:
                    pair = ("X", "Y")
                else:
                    pair = ("X", "X") if i % 2 else ("Y", "Y")
                pairs.append(pair)
                clusters.append(f"conv_{c}")
        return pairs, clusters

    def run(self, pairs, clusters, *, unit, seed=0, resamples=300):
        return kappa.bootstrap_ci(
            pairs, clusters, kappa.cohen_kappa, unit=unit, resamples=resamples, seed=seed,
            level=thresholds.BOOTSTRAP_CI_LEVEL,
            max_undefined_fraction=thresholds.UNDEFINED_REPLICATE_MAX_FRACTION)

    def test_the_same_seed_gives_the_same_interval(self):
        pairs, clusters = self.build(8, 5)
        first = self.run(pairs, clusters, unit="conversation")
        second = self.run(pairs, clusters, unit="conversation")
        assert (first["low"], first["high"]) == (second["low"], second["high"])

    def test_a_different_seed_can_give_a_different_interval(self):
        pairs, clusters = self.build(8, 5)
        first = self.run(pairs, clusters, unit="conversation", seed=0)
        second = self.run(pairs, clusters, unit="conversation", seed=1)
        assert (first["low"], first["high"]) != (second["low"], second["high"])

    def test_the_interval_brackets_the_point_estimate(self):
        pairs, clusters = self.build(10, 6)
        point = kappa.cohen_kappa(pairs)
        interval = self.run(pairs, clusters, unit="conversation")
        assert interval["low"] <= point <= interval["high"]

    def test_clustering_by_conversation_is_wider_than_treating_items_as_independent(self):
        """The reason conversation is the primary unit.

        Items from one conversation share its context, so resampling items as if they were
        independent understates the uncertainty. This is the asymmetry that choice rests on.
        """
        pairs, clusters = self.build(8, 10)
        width = lambda ci: ci["high"] - ci["low"]
        # Averaged over several seeds, so the test asserts the asymmetry rather than one
        # lucky resample sequence.
        by_conversation = [width(self.run(pairs, clusters, unit="conversation", seed=s))
                           for s in range(5)]
        by_item = [width(self.run(pairs, clusters, unit="item", seed=s)) for s in range(5)]
        mean = lambda xs: sum(xs) / len(xs)
        assert mean(by_conversation) > mean(by_item)

    def test_the_unit_is_recorded_in_the_result(self):
        pairs, clusters = self.build(4, 4)
        assert self.run(pairs, clusters, unit="conversation")["unit"] == "conversation"
        assert self.run(pairs, clusters, unit="item")["unit"] == "item"

    def test_an_unknown_unit_is_an_error(self):
        pairs, clusters = self.build(2, 2)
        with pytest.raises(ValueError, match="unknown bootstrap unit"):
            self.run(pairs, clusters, unit="turn")

    def test_undefined_replicates_are_counted_not_silently_dropped(self):
        """A category in one conversation out of many.

        Most conversation-level resamples miss it entirely, so most replicates have no defined
        kappa. The interval must say so rather than quietly describe the lucky subset.
        """
        pairs = [("RARE", "RARE")] + [("NO-OP", "NO-OP")] * 39
        clusters = ["conv_rare"] + [f"conv_{i // 4}" for i in range(39)]
        result = kappa.bootstrap_ci(
            pairs, clusters, lambda p: kappa.one_vs_rest_kappa(p, "RARE"),
            unit="conversation", resamples=300, seed=0,
            level=thresholds.BOOTSTRAP_CI_LEVEL,
            max_undefined_fraction=thresholds.UNDEFINED_REPLICATE_MAX_FRACTION)
        assert result["undefined_replicates"] > 0
        assert result["interpretable"] is False
        assert "undefined" in result["reason"]

    def test_all_undefined_says_so_and_reports_no_bounds(self):
        pairs = [("NO-OP", "NO-OP")] * 10
        clusters = ["conv_0"] * 10
        result = self.run(pairs, clusters, unit="conversation", resamples=50)
        assert result["low"] is None and result["high"] is None
        assert result["interpretable"] is False
        assert result["reason"] == "every resample gave an undefined statistic"
