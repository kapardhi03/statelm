"""Tests for the cosine and nearest-neighbour code.

A stub embedder stands in for the real models, so these run with no network and no weights.
Expected values are arithmetic, computed by hand.
"""

from __future__ import annotations

import numpy as np
import pytest

import similarity
import thresholds


class StubEmbedder:
    """Returns a fixed vector per text. `encode` is the only thing the audit needs."""

    name = "stub"
    revision = "0" * 40

    def __init__(self, table: dict[str, list[float]]) -> None:
        self.table = table

    def encode(self, texts):
        return np.array([self.table[t] for t in texts], dtype=np.float64)


class TestEmbeddingInput:
    def test_uses_the_pre_registered_template(self):
        assert similarity.embedding_input("city", "the city") == "city: the city"

    def test_no_service_information_leaks_in(self):
        text = similarity.embedding_input("city", "the city")
        assert "Buses" not in text and text.count(":") == 1

    def test_template_is_the_one_whose_hash_is_recorded(self):
        assert thresholds.EMBEDDING_INPUT_TEMPLATE == "{name}: {description}"


class TestCosine:
    def test_identical_vectors(self):
        assert similarity.cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)

    def test_orthogonal_vectors(self):
        assert similarity.cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)

    def test_opposite_vectors(self):
        assert similarity.cosine([1.0, 0.0], [-1.0, 0.0]) == pytest.approx(-1.0)

    def test_scale_invariance(self):
        assert similarity.cosine([3.0, 4.0], [6.0, 8.0]) == pytest.approx(1.0)

    def test_hand_computed_angle(self):
        # 45 degrees between (1,0) and (1,1): cos = 1/sqrt(2)
        assert similarity.cosine([1.0, 0.0], [1.0, 1.0]) == pytest.approx(1 / np.sqrt(2))

    def test_zero_vector_is_zero_not_nan(self):
        assert similarity.cosine([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_threshold_boundary_is_inclusive(self):
        # Constructed to sit exactly on 0.8: (0.8, 0.6) against (1, 0).
        value = similarity.cosine([0.8, 0.6], [1.0, 0.0])
        assert value == pytest.approx(0.8)
        assert value >= thresholds.COSINE_THRESHOLD


class TestL2Normalize:
    def test_rows_become_unit_length(self):
        out = similarity.l2_normalize(np.array([[3.0, 4.0], [1.0, 0.0]]))
        assert np.allclose(np.linalg.norm(out, axis=1), 1.0)

    def test_zero_row_stays_zero(self):
        out = similarity.l2_normalize(np.array([[0.0, 0.0], [3.0, 4.0]]))
        assert np.allclose(out[0], [0.0, 0.0])
        assert not np.isnan(out).any()

    def test_rejects_non_matrix(self):
        with pytest.raises(ValueError, match="2-D matrix"):
            similarity.l2_normalize(np.array([1.0, 2.0]))


class TestPairedCosine:
    def test_rowwise_values(self):
        left = np.array([[1.0, 0.0], [1.0, 0.0], [1.0, 0.0]])
        right = np.array([[1.0, 0.0], [0.0, 1.0], [-1.0, 0.0]])
        assert similarity.paired_cosine(left, right) == pytest.approx([1.0, 0.0, -1.0])

    def test_shape_mismatch_raises_rather_than_broadcasting(self):
        with pytest.raises(ValueError, match="matching shapes"):
            similarity.paired_cosine(np.ones((2, 2)), np.ones((3, 2)))


class TestNearest:
    def test_picks_the_highest_scoring_candidate(self):
        queries = np.array([[1.0, 0.0]])
        candidates = np.array([[0.0, 1.0], [0.9, 0.1], [1.0, 0.0]])
        keys = [("s", "orthogonal"), ("s", "close"), ("s", "exact")]
        [(key, score)] = similarity.nearest(queries, candidates, keys)
        assert key == ("s", "exact")
        assert score == pytest.approx(1.0)

    def test_ties_break_on_sorted_key_not_input_order(self):
        queries = np.array([[1.0, 0.0]])
        vec = [1.0, 0.0]
        forward = similarity.nearest(
            queries, np.array([vec, vec]), [("s", "b_name"), ("s", "a_name")]
        )
        reverse = similarity.nearest(
            queries, np.array([vec, vec]), [("s", "a_name"), ("s", "b_name")]
        )
        assert forward[0][0] == reverse[0][0] == ("s", "a_name")

    def test_one_result_per_query_in_query_order(self):
        queries = np.array([[1.0, 0.0], [0.0, 1.0]])
        candidates = np.array([[1.0, 0.0], [0.0, 1.0]])
        keys = [("s", "x"), ("s", "y")]
        out = similarity.nearest(queries, candidates, keys)
        assert [k for k, _ in out] == [("s", "x"), ("s", "y")]

    def test_empty_candidate_set_raises(self):
        with pytest.raises(ValueError, match="empty candidate set"):
            similarity.nearest(np.array([[1.0, 0.0]]), np.zeros((0, 2)), [])

    def test_key_count_must_match_candidate_count(self):
        with pytest.raises(ValueError, match="keys for"):
            similarity.nearest(np.array([[1.0, 0.0]]), np.ones((2, 2)), [("s", "only-one")])


class TestWithStubEmbedder:
    def test_end_to_end_nearest_through_an_embedder(self):
        table = {
            "city: the city": [1.0, 0.0],
            "town: the town": [0.99, 0.141],
            "price: the price": [0.0, 1.0],
        }
        embedder = StubEmbedder(table)
        candidates = embedder.encode(["town: the town", "price: the price"])
        queries = embedder.encode(["city: the city"])
        keys = [("Train", "town"), ("Train", "price")]
        [(key, score)] = similarity.nearest(queries, candidates, keys)
        assert key == ("Train", "town")
        assert score >= thresholds.COSINE_THRESHOLD
