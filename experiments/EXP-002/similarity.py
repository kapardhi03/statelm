"""Embedding similarity for EXP-002 H1 and H2.

The cosine and nearest-neighbour code is pure and tested with a stub embedder. Loading a real
model is confined to `SentenceTransformerEmbedder`, which the tests never touch, so the measures
can be verified without downloading anything.

Every embedder returns L2-normalized rows, so a dot product is a cosine.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

import numpy as np

import thresholds


class Embedder(Protocol):
    """What the audit needs from a model: a name, a pinned revision, and `encode`."""

    name: str
    revision: str

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        """Return an (len(texts), dim) float array whose rows are L2-normalized."""


def embedding_input(name: str, description: str) -> str:
    """The pre-registered template: raw name, no service information."""
    return thresholds.EMBEDDING_INPUT_TEMPLATE.format(name=name, description=description)


def l2_normalize(matrix: np.ndarray) -> np.ndarray:
    """Row-wise L2 normalization. A zero row stays zero rather than becoming NaN."""
    m = np.asarray(matrix, dtype=np.float64)
    if m.ndim != 2:
        raise ValueError(f"expected a 2-D matrix, got shape {m.shape}")
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    return m / norms


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity of two vectors, normalizing defensively."""
    va = np.asarray(a, dtype=np.float64)
    vb = np.asarray(b, dtype=np.float64)
    na, nb = np.linalg.norm(va), np.linalg.norm(vb)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(va, vb) / (na * nb))


def paired_cosine(left: np.ndarray, right: np.ndarray) -> np.ndarray:
    """Row-wise cosine between two equally shaped matrices."""
    a, b = np.asarray(left, dtype=np.float64), np.asarray(right, dtype=np.float64)
    if a.shape != b.shape:
        raise ValueError(f"paired_cosine needs matching shapes, got {a.shape} and {b.shape}")
    return np.sum(l2_normalize(a) * l2_normalize(b), axis=1)


def nearest(
    queries: np.ndarray, candidates: np.ndarray, keys: Sequence[tuple]
) -> list[tuple[tuple, float]]:
    """Nearest candidate per query row, as (key, cosine).

    Ties break on the candidate key's sorted order, not on input order: candidates are sorted
    by key first, so `argmax` returns the smallest key among equal scores. Two slots sharing a
    name and a description do occur across services, so ties are real rather than theoretical.
    """
    if len(keys) != len(candidates):
        raise ValueError(f"{len(keys)} keys for {len(candidates)} candidates")
    if len(keys) == 0:
        raise ValueError("cannot take a nearest neighbour from an empty candidate set")
    order = sorted(range(len(keys)), key=lambda i: keys[i])
    sorted_keys = [keys[i] for i in order]
    sims = l2_normalize(queries) @ l2_normalize(candidates[order]).T
    best = sims.argmax(axis=1)
    return [(sorted_keys[j], float(sims[i, j])) for i, j in enumerate(best)]


class SentenceTransformerEmbedder:
    """A sentence-transformers model, pinned to a resolved commit sha.

    The revision is resolved from the Hub before loading and recorded, so a run config names the
    exact weights rather than whatever "main" pointed at that day.
    """

    def __init__(self, model_id: str, batch_size: int = 64) -> None:
        from huggingface_hub import model_info
        from sentence_transformers import SentenceTransformer

        self.name = model_id
        self.revision = model_info(model_id).sha
        self.batch_size = batch_size
        self._model = SentenceTransformer(model_id, revision=self.revision)

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        return self._model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
