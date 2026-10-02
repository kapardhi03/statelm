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
