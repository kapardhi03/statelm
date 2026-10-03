"""Verifies with git itself that no scrubber output can be committed.

The privacy rule for EXP-000 is that client text never leaves the local machine. `.gitignore`
is the mechanism, so this asserts the mechanism rather than trusting it, and includes a negative
control so the test can actually fail.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]

MUST_BE_IGNORED = [
    "data/raw/arthryx/export.csv",
    "data/raw/arthryx/export.xlsx",
    "data/raw/arthryx/export.json",
    "data/scrubbed/EXP-000/conv_001.jsonl",
    "data/scrubbed/EXP-000/_audit/audit.sensitive.jsonl",
    "data/scrubbed/EXP-000/summary.json",
    # The sampler's manifest holds every item's stratum and source. It stays local: those are
    # the counts an annotator must not meet before labelling.
    "data/scrubbed/EXP-000-annotation/manifest.json",
    # A run directory holds counts; anything else under it is not a summary and stays local.
    "runs/EXP-000/20261003T000000Z-abc1234/stdout.log",
    "runs/EXP-000/20261003T000000Z-abc1234/synthetic_census.json",
]

MUST_NOT_BE_IGNORED = [
    "experiments/EXP-000/scrub.py",
    "docs/research/experiments/EXP-000-label-feasibility.md",
    # Run summaries are counts only and are tracked on purpose: a figure that lives on one
    # machine rests on a report, which is what the v2 and v3 censuses did.
    "runs/EXP-000/20261003T000000Z-abc1234/config.json",
    "runs/EXP-000/20261003T000000Z-abc1234/census.json",
    "runs/EXP-000/20261003T000000Z-abc1234/cue_diagnostics.json",
]


def is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO, capture_output=True, check=False,
    )
    if result.returncode not in (0, 1):
        pytest.skip(f"git check-ignore unavailable: {result.stderr.decode().strip()}")
    return result.returncode == 0


@pytest.fixture(scope="module", autouse=True)
def require_repo():
    if not (REPO / ".git").exists():
        pytest.skip("not a git checkout")


@pytest.mark.parametrize("path", MUST_BE_IGNORED)
def test_client_text_paths_cannot_be_committed(path):
    assert is_ignored(path), f"{path} is NOT gitignored; client text could be committed"


@pytest.mark.parametrize("path", MUST_NOT_BE_IGNORED)
def test_the_check_discriminates(path):
    # Negative control: if everything looked ignored, the test above would prove nothing.
    assert not is_ignored(path), f"{path} should be committable"
