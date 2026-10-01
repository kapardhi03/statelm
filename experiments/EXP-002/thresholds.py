"""Pre-registered thresholds for EXP-002.

Every number in this module is fixed in
`docs/research/experiments/EXP-002-schema-novelty-audit.md` BEFORE any run. Changing one
requires a Change log entry in that file, written by the researcher. Nothing here may be
altered after seeing a result.
"""

from __future__ import annotations

# Step 1 gate, on (service, slot) instances with raw (N0) names.
GATE_SLOT_BAND: tuple[float, float] = (60.0, 70.0)
GATE_INTENT_BAND: tuple[float, float] = (66.0, 76.0)

# Used from Step 2 onward. Recorded here so the whole pre-registration sits in one file.
COSINE_THRESHOLD: float = 0.8
JACCARD_THRESHOLD: float = 0.5
H1_MIN_RATE: float = 50.0
H2_C1_MAX_EXACT_RATE: float = 70.0
H2_C2_MIN_RETAINED: float = 80.0

EMBEDDING_INPUT_TEMPLATE: str = "{name}: {description}"


def in_band(value: float, band: tuple[float, float]) -> bool:
    """Inclusive at both ends: a rate sitting exactly on a band edge passes."""
    low, high = band
    return low <= value <= high
