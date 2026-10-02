"""Write containment for EXP-000's local tools.

Every write in this package goes through `open_for_write`, which refuses any path outside the
output root the operator passed in. That is a guarantee this tool makes about itself, so it is
enforced in one place and covered by tests rather than left to discipline.
"""

from __future__ import annotations

import json
from pathlib import Path


class OutsideOutputRoot(Exception):
    """Raised when a write would land outside the operator's chosen output folder."""


def resolve_root(output_dir: str | Path) -> Path:
    return Path(output_dir).expanduser().resolve()


def assert_within(root: Path, target: str | Path) -> Path:
    """Return the resolved target, or raise if it is not inside `root`.

    Resolution happens before the comparison, so `..` segments and symlinked parents cannot
    walk out of the root.
    """
    root = root.resolve()
    candidate = Path(target).expanduser()
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = candidate.resolve()
    if candidate != root and root not in candidate.parents:
        raise OutsideOutputRoot(f"{candidate} is outside the output root {root}")
    return candidate


def assert_disjoint(input_dir: str | Path, output_dir: str | Path) -> None:
    """Refuse an input and output that nest, which would let a run read its own output."""
    src = Path(input_dir).expanduser().resolve()
    dst = Path(output_dir).expanduser().resolve()
    if src == dst:
        raise OutsideOutputRoot(f"input and output are the same folder: {src}")
    if src in dst.parents:
        raise OutsideOutputRoot(f"output {dst} is inside input {src}")
    if dst in src.parents:
        raise OutsideOutputRoot(f"input {src} is inside output {dst}")


def open_for_write(root: Path, target: str | Path, *, dry_run: bool = False):
    """Context-managed text write, contained in `root`. Under dry_run nothing is opened."""
    path = assert_within(root, target)
    if dry_run:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    return path.open("w", encoding="utf-8")


def write_text(root: Path, target: str | Path, text: str, *, dry_run: bool = False) -> Path:
    path = assert_within(root, target)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return path


def write_json(root: Path, target: str | Path, obj, *, dry_run: bool = False) -> Path:
    return write_text(root, target, json.dumps(obj, indent=2, ensure_ascii=False) + "\n",
                      dry_run=dry_run)


def write_jsonl(root: Path, target: str | Path, rows, *, dry_run: bool = False) -> Path:
    body = "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    return write_text(root, target, body, dry_run=dry_run)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def data_scrubbed_root(root: Path | None = None) -> Path:
    return ((root or repo_root()) / "data" / "scrubbed").resolve()


def assert_in_data_scrubbed(target: str | Path, *, allowed_root: Path | None = None) -> Path:
    """Resolve a path and refuse anything outside `data/scrubbed/`.

    The disagreement list holds item ids, both labels and, for value disagreements, both
    values. That is client-derived content, so it may only land in the gitignored tree.
    `allowed_root` exists so tests can point at a temporary directory.
    """
    root = (allowed_root or data_scrubbed_root()).resolve()
    path = Path(target).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path != root and root not in path.parents:
        raise OutsideOutputRoot(
            f"{path} is outside {root}; the disagreement list is written only to data/scrubbed/")
    return path


def runs_root(experiment: str, root: Path | None = None) -> Path:
    return ((root or repo_root()) / "runs" / experiment).resolve()


def assert_in_runs(target: str | Path, experiment: str, *,
                   allowed_root: Path | None = None) -> Path:
    """Resolve a path and refuse anything outside `runs/<experiment>/`.

    Only aggregates go here, and this tree is partly tracked by git, so the containment check
    is what keeps a stray output path from putting client-derived content under version control.
    """
    root = (allowed_root or runs_root(experiment)).resolve()
    path = Path(target).expanduser()
    if not path.is_absolute():
        path = root / path
    path = path.resolve()
    if path != root and root not in path.parents:
        raise OutsideOutputRoot(f"{path} is outside {root}; aggregates go only to runs/{experiment}/")
    return path
