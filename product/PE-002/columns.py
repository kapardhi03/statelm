"""Mapping from PE-001's logical fields to the labelling sheet's column names.

The sheet is Kapardhi's (Q1d, 2026-11-08) and its headers are not known to this repository, so the
mapping is configuration rather than a constant. `columns.example.yaml` is tracked and carries the
logical names; the real `columns.yaml` is his to write once, and `--print-columns` prints the
export's actual headers so he can fill it without opening the file in an editor.

Header names are not client text, so a filled-in `columns.yaml` is safe to commit. It is not
gitignored, deliberately: the mapping is part of how a run is reproduced, and its hash goes into
`config.json`.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from pathlib import Path

import yaml

REQUIRED = ("conversation_id", "user_message", "action")
OPTIONAL = ("turn_index", "reply", "labeler", "item_id")


@dataclass(frozen=True)
class Columns:
    """Sheet column names, by logical field."""

    conversation_id: str
    user_message: str
    action: str
    turn_index: str | None = None
    reply: str | None = None
    labeler: str | None = None
    item_id: str | None = None

    @classmethod
    def load(cls, path: Path) -> "Columns":
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a mapping of logical field -> column name")
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(raw) - known)
        if unknown:
            raise ValueError(
                f"{path}: unknown logical field(s) {unknown}. Known fields: {sorted(known)}"
            )
        missing = [k for k in REQUIRED if not raw.get(k)]
        if missing:
            raise ValueError(f"{path}: these logical fields are required and unset: {missing}")
        return cls(**{k: (v if v else None) for k, v in raw.items()})

    def present(self) -> dict[str, str]:
        """Logical field -> column name, for the fields that are mapped."""
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name)}

    def validate_against(self, header: list[str]) -> None:
        """Raise unless every mapped column exists in the export's header row.

        The error names the export's real headers, because the common failure here is a guess at a
        column name and the fix is mechanical once the headers are in view. Header names are not
        client text, so printing them leaks nothing.
        """
        have = set(header)
        missing = {k: v for k, v in self.present().items() if v not in have}
        if missing:
            raise ValueError(
                "columns.yaml names columns that are not in the export.\n"
                + "".join(f"  {k}: {v!r} not found\n" for k, v in sorted(missing.items()))
                + f"The export's headers are: {header}"
            )

    def sha256(self) -> str:
        """A hash of the mapping, so `config.json` records which mapping a run used."""
        blob = "\n".join(f"{k}={v}" for k, v in sorted(self.present().items()))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()
