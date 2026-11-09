"""The ladder's rungs, and the provider table they are wired to.

A rung is a named combination of: which prompt template, whether the answer is constrained to the
vocabulary, whether examples are included, and which provider entry runs it. Everything else is
shared, so a difference between two rungs is the thing that rung is defined to isolate.

Which models B4 and B5 are is **Q7**, unanswered, so it is configuration (`providers.yaml`) rather
than a constant. `providers.example.yaml` shows the shape and carries defaults that are a starting
point, not a decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from backends import AnthropicBackend, Backend, OpenAICompatibleBackend
from prompts import B0_PROMPT_FILE, B1_PROMPT_FILE

MODEL_RUNGS = ("B0", "B1", "B2", "B3", "B4", "B5")


@dataclass(frozen=True)
class Rung:
    name: str
    prompt_file: str
    constrained: bool
    fewshot: bool
    isolates: str


LADDER: dict[str, Rung] = {
    "B0": Rung("B0", B0_PROMPT_FILE, False, False, "where the product actually is"),
    "B1": Rung("B1", B1_PROMPT_FILE, False, False, "how much of the gap is prompt quality"),
    "B2": Rung("B2", B1_PROMPT_FILE, True, False, "how much is format compliance"),
    "B3": Rung("B3", B1_PROMPT_FILE, False, True, "the rung PE-003 must beat"),
    "B4": Rung("B4", B1_PROMPT_FILE, False, False, "frontier headroom"),
    "B5": Rung("B5", B1_PROMPT_FILE, False, False, "a second frontier vendor"),
}


@dataclass(frozen=True)
class ProviderEntry:
    key: str
    backend: str
    provider: str
    model: str
    price_input_per_mtok: float
    price_output_per_mtok: float
    options: dict[str, Any]

    def build(self, name: str) -> Backend:
        if self.backend == "anthropic":
            return AnthropicBackend(
                name=name,
                model=self.model,
                effort=str(self.options.get("effort", "low")),
                max_tokens=int(self.options.get("max_tokens", 256)),
            )
        if self.backend == "openai_compatible":
            return OpenAICompatibleBackend(
                name=name,
                provider=self.provider,
                model=self.model,
                base_url=self.options.get("base_url"),
                api_key_env=self.options.get("api_key_env"),
                temperature=self.options.get("temperature", 0.0),
                max_tokens=int(self.options.get("max_tokens", 256)),
                extra_body=self.options.get("extra_body"),
            )
        raise ValueError(
            f"provider {self.key!r}: unknown backend {self.backend!r}; "
            "expected 'anthropic' or 'openai_compatible'"
        )

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (
            input_tokens / 1_000_000 * self.price_input_per_mtok
            + output_tokens / 1_000_000 * self.price_output_per_mtok
        )


@dataclass(frozen=True)
class Providers:
    by_rung: dict[str, str]
    entries: dict[str, ProviderEntry]
    price_table_version: str
    source_sha256: str

    @classmethod
    def load(cls, path: Path) -> "Providers":
        import hashlib

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError(f"{path}: expected a mapping with 'rungs' and 'providers'")
        if not raw.get("price_table_version"):
            raise ValueError(
                f"{path}: price_table_version is required. Prices move — the Tinker catalogue "
                "changed three models' availability inside a month — so a cost figure that does "
                "not name which table it came from cannot be checked later."
            )

        entries: dict[str, ProviderEntry] = {}
        for key, spec in (raw.get("providers") or {}).items():
            if not isinstance(spec, dict):
                raise ValueError(f"{path}: provider {key!r} must be a mapping")
            for required in ("backend", "provider", "model", "price_per_mtok"):
                if not spec.get(required):
                    raise ValueError(f"{path}: provider {key!r} is missing {required!r}")
            price = spec["price_per_mtok"]
            if not isinstance(price, dict) or "input" not in price or "output" not in price:
                raise ValueError(
                    f"{path}: provider {key!r} price_per_mtok needs 'input' and 'output'"
                )
            options = {
                k: v
                for k, v in spec.items()
                if k not in ("backend", "provider", "model", "price_per_mtok")
            }
            entries[key] = ProviderEntry(
                key=key,
                backend=str(spec["backend"]),
                provider=str(spec["provider"]),
                model=str(spec["model"]),
                price_input_per_mtok=float(price["input"]),
                price_output_per_mtok=float(price["output"]),
                options=options,
            )

        by_rung: dict[str, str] = {}
        for rung, spec in (raw.get("rungs") or {}).items():
            if rung not in LADDER:
                raise ValueError(f"{path}: unknown rung {rung!r}; expected one of {MODEL_RUNGS}")
            ref = (spec or {}).get("provider_ref") if isinstance(spec, dict) else None
            if not ref:
                raise ValueError(f"{path}: rung {rung!r} needs a provider_ref")
            if ref not in entries:
                raise ValueError(f"{path}: rung {rung!r} references unknown provider {ref!r}")
            by_rung[rung] = str(ref)

        if not by_rung:
            raise ValueError(f"{path}: no rungs configured")
        return cls(
            by_rung=by_rung,
            entries=entries,
            price_table_version=str(raw["price_table_version"]),
            source_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )

    def providers_reached(self, rungs: list[str]) -> set[str]:
        """Which provider names a run would send client text to. The consent gate checks these."""
        return {self.entries[self.by_rung[r]].provider for r in rungs if r in self.by_rung}

    def as_config(self) -> dict[str, Any]:
        return {
            "price_table_version": self.price_table_version,
            "providers_sha256": self.source_sha256,
            "rung_to_provider": dict(sorted(self.by_rung.items())),
            "provider_models": {
                k: {"backend": e.backend, "provider": e.provider, "model": e.model}
                for k, e in sorted(self.entries.items())
            },
        }
