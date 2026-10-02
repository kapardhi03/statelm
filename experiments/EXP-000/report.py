"""The two reports.

`_audit/audit.sensitive.jsonl` contains the original text of every replacement, because that is
the only way to spot-check a redaction. It is therefore exactly as sensitive as the input, and it
carries a header row saying so.

`summary.json` contains counts and nothing else: no originals, no message text. It is the only
artifact intended to be copied into `runs/EXP-000/`.
"""

from __future__ import annotations

from dataclasses import dataclass

AUDIT_WARNING = (
    "THIS FILE CONTAINS UNREDACTED CLIENT PII. It exists so the operator can spot-check every "
    "replacement. Never commit it, never copy it out of the local machine, and delete it when "
    "the spot-check is done."
)


@dataclass(frozen=True)
class AuditEntry:
    conversation_id: str
    turn_index: int
    source_file: str
    source_row: int
    category: str
    original: str
    token: str

    def as_dict(self) -> dict:
        return {
            "record": "replacement",
            "conversation_id": self.conversation_id,
            "turn_index": self.turn_index,
            "source_file": self.source_file,
            "source_row": self.source_row,
            "category": self.category,
            "original": self.original,
            "token": self.token,
        }


def audit_rows(
    entries: list[AuditEntry],
    conversation_ids: dict[str, str],
    speaker_tokens: dict[str, dict[str, str]],
) -> list[dict]:
    """Header, then the id maps, then one row per replacement."""
    rows: list[dict] = [{"record": "warning", "message": AUDIT_WARNING}]
    rows += [
        {"record": "conversation_id_map", "source_conversation_id": src, "conversation_id": dst}
        for src, dst in conversation_ids.items()
    ]
    rows += [
        {"record": "speaker_map", "conversation_id": conv, "speaker": name, "speaker_id": token}
        for conv, speakers in speaker_tokens.items()
        for name, token in speakers.items()
    ]
    rows += [e.as_dict() for e in entries]
    return rows


def summary(
    *,
    files_read: list[str],
    conversations: dict[str, int],
    category_counts: dict[str, int],
    distinct_per_category: dict[str, int],
    unmapped_speakers: list[str],
    unparsed_timestamps: int,
    settings: dict,
    residual: dict | None = None,
) -> dict:
    """Counts only. Anything that could carry client text is deliberately absent."""
    return {
        "tool": "EXP-000 scrub.py",
        "contains_client_text": False,
        "files_read": files_read,
        "conversation_count": len(conversations),
        "messages_per_conversation": conversations,
        "message_count": sum(conversations.values()),
        "replacements_by_category": category_counts,
        "distinct_entities_by_category": distinct_per_category,
        "unmapped_speakers_count": len(unmapped_speakers),
        "unmapped_speakers": sorted(unmapped_speakers),
        "unparsed_timestamps": unparsed_timestamps,
        "settings": settings,
        "residual_scan": residual,
        "caveats": [
            "This is a first-pass redactor, not a guarantee of de-identification.",
            "PERSON detection is roster-only: a third party named in passing is not detected.",
            "ADDRESS is the weakest category; keyword-anchored clauses are blunt and every one "
            "is listed in the audit report.",
            "Bare amounts are preserved by design, because EXP-000's labels depend on them.",
        ],
    }
