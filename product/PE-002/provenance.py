"""Run identity for PE-001: the run id, the git state, and the input hashes.

CLAUDE.md requires every run to write `config.json` with the git commit, the seed, the data hashes
and the versions it used. The same discipline applies here, with one addition the product track
needs: `config.json` records whether the tree was dirty, because a figure produced from uncommitted
code cannot be re-derived from the commit it names.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_VERSION = "PE-001-audit-1"


def _git(*args: str, cwd: Path) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, check=False, timeout=15
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode().strip() if out.returncode == 0 else None


def git_state(repo: Path) -> dict[str, Any]:
    commit = _git("rev-parse", "HEAD", cwd=repo)
    status = _git("status", "--porcelain", cwd=repo)
    return {
        "git_commit": commit or "unknown",
        "git_tree_dirty": bool(status) if status is not None else None,
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run_id(repo: Path) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    commit = _git("rev-parse", "--short=7", "HEAD", cwd=repo) or "nogit"
    return f"{stamp}-{commit}"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
