"""The Q9 gate: stage 2 cannot send client text anywhere without a recorded decision.

`.claude/rules/data-privacy.md` says client conversation text is "never requested, read, committed
or uploaded, scrubbed or not". Kapardhi's answer to Q2 on 2026-10-10 was "client. consent is taken
and can be used also i g wehave >400 examples" — hedged, and about *using* the data. The plan's
§3.1 therefore does not treat hosted training as unblocked, and §9's **Q9** asks whether the consent
on file covers upload to a third-party API with durable retention.

Stage 2 is the first step in the whole plan that uploads. That is not recoverable, so the gate is
code rather than discipline: no consent record, no requests. The record also has to name every
provider a run would reach, so that adding a provider later is a visible decision and not a
config edit.

Nothing here decides whether consent exists. It checks that a decision was written down, and makes
the run config carry what was written.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import yaml

REQUIRED_FIELDS = ("instructed_on", "instruction_verbatim", "providers", "data_slice")


class ConsentError(RuntimeError):
    """Raised when stage 2 is asked to upload without a usable consent record."""


@dataclass(frozen=True)
class Consent:
    instructed_on: date
    instruction_verbatim: str
    providers: tuple[str, ...]
    data_slice: str
    source_path: Path
    sha256: str

    @classmethod
    def load(cls, path: Path) -> "Consent":
        if not path.exists():
            raise ConsentError(
                f"{path} does not exist.\n"
                "Stage 2 uploads client conversation text to a third party, which the plan's §3.1 "
                "gates on Q9 and which cannot be undone. Record the decision first: copy "
                "consent.example.yaml, fill in the date, Kapardhi's instruction verbatim, every "
                "provider a run may reach, and which data slice it covers."
            )
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ConsentError(f"{path}: expected a mapping with {list(REQUIRED_FIELDS)}")

        missing = [f for f in REQUIRED_FIELDS if not raw.get(f)]
        if missing:
            raise ConsentError(f"{path}: these fields are required and unset: {missing}")

        instructed = raw["instructed_on"]
        if isinstance(instructed, str):
            instructed = date.fromisoformat(instructed)
        if not isinstance(instructed, date):
            raise ConsentError(f"{path}: instructed_on must be a date (YYYY-MM-DD)")

        providers = raw["providers"]
        if not isinstance(providers, list) or not all(isinstance(p, str) and p for p in providers):
            raise ConsentError(f"{path}: providers must be a non-empty list of provider names")

        verbatim = str(raw["instruction_verbatim"]).strip()
        if len(verbatim) < 10:
            raise ConsentError(
                f"{path}: instruction_verbatim looks like a placeholder. It should be what he "
                "actually said, quoted, so the record shows what was authorised rather than that "
                "someone ticked a box."
            )

        return cls(
            instructed_on=instructed,
            instruction_verbatim=verbatim,
            providers=tuple(sorted(providers)),
            data_slice=str(raw["data_slice"]).strip(),
            source_path=path,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def authorises(self, provider: str) -> bool:
        return provider in self.providers

    def require(self, providers: set[str]) -> None:
        """Raise unless every provider a run would reach is named in the record."""
        unauthorised = sorted(p for p in providers if not self.authorises(p))
        if unauthorised:
            raise ConsentError(
                f"{self.source_path} does not name these provider(s): {unauthorised}. "
                f"It names {list(self.providers)}. Adding a provider is a decision for Kapardhi, "
                "not a config edit: have him say so, record it, then re-run."
            )

    def as_config(self) -> dict[str, object]:
        """What the run config records. The verbatim instruction is deliberately NOT included.

        It is his words, it lives in the consent file and in the plan's §0, and a run config is
        copied into reports. The hash ties the run to the exact file that authorised it, which is
        what a later reader needs.
        """
        return {
            "consent_sha256": self.sha256,
            "consent_instructed_on": self.instructed_on.isoformat(),
            "consent_providers": list(self.providers),
        }
