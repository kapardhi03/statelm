"""Run provenance: what ties a set of numbers to a commit and a corpus.

Written because of the v2 and v3 censuses. Both were reported as counts in a message, with no
run directory, so nothing tied "135 eligible customer turns" to a commit, to a code version
holding the cue lists the count was measured with, or to the corpus it was measured over. The
experiment record had to say the figures rested on a report rather than on an auditable record.
A number that cannot be re-derived cannot be checked, and CLAUDE.md asks every run for one of
these.

No client text passes through here. A corpus is represented by a file count and one hash; the
file names are conversation ids, so they go into the hash input and never into the output.
"""

from __future__ import annotations

import hashlib
import platform
import subprocess
import time
from collections.abc import Iterable
from pathlib import Path

EXPERIMENT = "EXP-000"


def git_output(*args: str) -> str:
    """A git field, or "unknown". Never raises: provenance must not fail a run."""
    try:
        return subprocess.run(("git", *args), capture_output=True, text=True,
                              check=True, cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def new_run_id() -> str:
    """`<UTC timestamp>-<short commit>`, the format the existing run directories use."""
    return (f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
            f"-{git_output('rev-parse', 'HEAD')[:7]}")


def corpus_hash(paths: Iterable[Path]) -> dict:
    """A corpus as `{files, sha256}`, never as a list of names.

    Each file's own digest is folded in with its name, in sorted name order, so the hash moves
    if a file changes, is added or is removed. The names are inside the hash input and not in
    the result: a conversation id is not something to write into a tracked file.
    """
    pairs = sorted((Path(p).name, sha256_file(p)) for p in paths)
    rolling = hashlib.sha256()
    for name, digest in pairs:
        rolling.update(f"{name}:{digest}\n".encode("utf-8"))
    return {"files": len(pairs), "sha256": rolling.hexdigest()}


def base_config(*, step: str, run_id: str, inputs: dict, extra: dict | None = None) -> dict:
    """The fields CLAUDE.md asks of every run's `config.json`.

    `model_name`, `model_revision` and `prompt_template_hash` are present and null on purpose:
    these steps run no model, and a missing key reads as an omission where an explicit null
    reads as "there was none".
    """
    config = {
        "experiment": EXPERIMENT,
        "step": step,
        "run_id": run_id,
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_tree_dirty": bool(git_output("status", "--porcelain")),
        "python": platform.python_version(),
        "platform": platform.platform(),
        "model_name": None,
        "model_revision": None,
        "prompt_template_hash": None,
        "inputs": inputs,
    }
    config.update(extra or {})
    return config


def repo_relative(path) -> str:
    """A path as the repository sees it, or just its name.

    `config.json` is tracked, and an absolute input path is a home directory. What the record
    needs is which corpus was read, which `corpus_hash` already answers; the path is only for
    orientation, so it is worth nothing to leak a machine layout for.
    """
    resolved = Path(path).expanduser().resolve()
    repo = (Path(__file__).parent / ".." / "..").resolve()
    try:
        return str(resolved.relative_to(repo))
    except ValueError:
        return resolved.name
