# EXP-000 PII scrubber

`scrub.py` turns your CSV / XLSX / JSON conversation exports into scrubbed JSONL, plus two
reports. **You run it on your machine. It never runs in a Claude session.**

## The privacy rule this tool exists to serve

Client text never leaves your machine. Every EXP-000 tool (this scrubber, the item sampler, the
annotation-sheet generator, the agreement script) runs locally. Only aggregate results — counts,
Cohen's κ, confusion matrices — go into `runs/EXP-000/`. Conversation text is never committed and
never requested, scrubbed or not.

`.gitignore` enforces the file-level half of that: `data/raw/` and `data/scrubbed/` are both
ignored, verified against `git check-ignore` in `tests/test_gitignore.py`, which includes a
negative control so the check can actually fail.

The rule is also written into `.claude/rules/data-privacy.md`, which carries no `paths`
frontmatter and so loads in every session regardless of which files it touches. `.claude/settings.json`
additionally denies the `Read` and `Edit` tools on `./data/raw/**` and `./data/scrubbed/**`.

> One gap worth knowing: a `deny` on `Read` and `Edit` does not cover `Bash`, so `cat data/raw/...`
> would still work. Closing that would mean denying Bash patterns too, which is a broader change
> to how the session can work in this repo — say the word if you want it.

## What this is, and what it is not

It is a **first-pass redactor that makes your spot-check tractable.** It is **not** a guarantee of
de-identification.

Structured identifiers (emails, phones, UPI, IFSC, cards, account numbers, transaction
references) are caught reliably. Names are caught **only when they appear in the export's own
speaker roster** — a third party named in passing is not detected. Addresses are the weakest
category by a distance. The audit report exists precisely because you have to be the final check.

## Install and run

```bash
cd experiments/EXP-000
uv sync                      # PyYAML + openpyxl, pytest for the tests
uv run pytest                # 89 tests, all on fabricated data, no network

cp columns.example.yaml columns.yaml && $EDITOR columns.yaml

# 1. Look before you write
uv run python scrub.py --input ../../data/raw/arthryx \
                       --output ../../data/scrubbed/EXP-000 \
                       --columns columns.yaml --dry-run

# 2. Write, and re-scan the output for anything missed
uv run python scrub.py --input ../../data/raw/arthryx \
                       --output ../../data/scrubbed/EXP-000 \
                       --columns columns.yaml --check
```

Then read `_audit/audit.sensitive.jsonl`, satisfy yourself, and delete it.

## `columns.yaml`

Your column names vary, so name them. Nothing is guessed: a mapped column that is absent is an
error, because reading the wrong column would corrupt the data with no visible symptom.

```yaml
conversation_id: conv_id      # required
speaker: from                 # required
timestamp: sent_at            # required
text: body                    # required
role: speaker_role            # optional
```

**Roles.** Taken from the `role` column when you map one. Otherwise pass `--roles roles.csv`
(`speaker,role` with values `customer` / `agent` / `bot`). Any speaker left unmapped becomes
`"unknown"` and is listed by name in `summary.json`.

**Dates.** ISO 8601 first, then common day-first formats, then `--date-format` if you pass one.
An unparseable value is kept verbatim in `timestamp_raw`, `timestamp` is null, and the count
appears in `summary.json` — a format problem is visible, never silent.

## What it writes

```
data/scrubbed/EXP-000/
  conv_001.jsonl                  one per conversation, scrubbed
  summary.json                    counts only; safe to copy into runs/EXP-000/
  _audit/
    audit.sensitive.jsonl         CONTAINS UNREDACTED PII
```

`audit.sensitive.jsonl` holds the original text of every replacement, because that is the only way
to spot-check a redaction. **It is as sensitive as your input.** It carries a warning as its first
record, it is gitignored, and you should delete it once you have reviewed it.

Conversation filenames are `conv_001`, not your source ids: an id like `ARTH-Priya` would leak the
thing we just removed. The source-id mapping is in the audit report only. `--keep-conversation-ids`
overrides this if you want source ids as filenames.

## Record schema

**EXP-000 pilot schema, not the StateLM data model (Stage 3 not started).**

```json
{"schema": "exp000-pilot-v1", "conversation_id": "conv_001", "turn_index": 0,
 "timestamp": "2025-08-12T19:42:13", "timestamp_raw": "2025-08-12 19:42:13",
 "speaker_id": "SPEAKER_1", "speaker_role": "customer",
 "text": "Hi, [PERSON_1] here. Budget is around 40 lakhs.",
 "provenance": {"source": "human", "generator": null, "labeler": null,
                "created_at": "...", "split": null, "scrubber_version": "0.1.0",
                "source_file": "arthryx.csv", "source_row": 0, "source_sha256": "..."}}
```

`labeler` is null because no labels exist yet, and the output carries **no derived fields at all**
— no `has_amount`, no entity tags, nothing that could prime an annotator. That follows the
record's own "must not do".

## Placeholders

`[PERSON_1]`, `[PHONE_1]`, numbered by first appearance, **scoped to one conversation**. The same
person in two conversations is `[PERSON_1]` in both and cannot be linked across them. Tokens are
never hashes of the original, since a hash is guessable from a small candidate set.

Surface variants collapse to one token: `Priya` and `Priya Sharma` are one person,
`+91 98765 43210` and `9876543210` are one phone. `SPEAKER_n` and `[PERSON_n]` use the same
ordinal for the same person.

## What each rule does, honestly

| Category | Rule | Recall |
|---|---|---|
| EMAIL | `local@domain` with a dot in the domain | high |
| UPI | `local@handle` with no dot (`name@okaxis`) | high |
| IFSC | `AAAA0999999` | high |
| CARD | 13–19 digits passing Luhn | high, few false positives |
| ACCOUNT | 11–18 digits, or 9–18 near an account keyword | high |
| TXNREF | 8–24 alphanumerics after UTR / txn / ref | moderate |
| PHONE | Indian mobile with or without `+91`/`0`, any separators; `+cc` international | high |
| AMOUNT | **preserved** unless within 60 characters of an account identifier | by design |
| PERSON | speaker roster only, full name and name parts | **misses third parties** |
| ADDRESS | pincodes and premise numbers (`Flat 402`, `H.No 3-4-12`, `Plot 17`); locality clauses opt-in | narrow by design |

### Why bare amounts are kept

EXP-000's labels include HEDGED, and its abstention taxonomy is built on examples like "around 40"
and "might stretch to 45". A scrubber that redacted amounts would delete the exact phenomenon the
experiment measures. So an amount is redacted **only** when it sits next to an account identifier —
the "payment of X to account Y" case. `--amount-window` changes the distance.

### Addresses: narrow by default, blunt only on request

**Default:** pincodes, plus premise designators after a keyword — `Flat 402`, `Flat No 402`,
`Flat 4B`, `H.No 3-4-12`, `House No 12`, `Plot 17`, `Door No 5`, `Villa 9`. Only the designator is
redacted, so the property type survives: `Flat 402, Sai Residency` becomes
`Flat [ADDRESS_1], Sai Residency`.

A locality or a road is **left alone**, because in a property conversation it is the state being
tracked rather than an identifier. `3BHK flat near Gachibowli, budget 80 lakhs` passes through
untouched, and there is a test that says so.

**Opt-in, with `--address-clauses`:** the old rule, running from a locality keyword (`road`,
`nagar`, `sector`, `landmark`, `opposite` and the rest) to the next comma or period. It removes
ordinary sentence text and it will eat location preferences. Every hit is in the audit report.

## The three guarantees, each covered by a test

1. **Writes nothing outside `--output`.** Every write passes through one containment check;
   `..`, absolute paths elsewhere, and symlinked parents are all refused.
2. **Never modifies your input.** Files are opened read-only; a test hashes the input tree before
   and after a full run.
3. **Makes no network call.** A test replaces `socket.socket`, `socket.create_connection` and
   `socket.getaddrinfo` with something that raises, then runs a complete scrub.

It also refuses to run when input and output nest, which would let a run read its own output.

## Known limits

- Roster-only names. No NER, by decision.
- Addresses are heuristic. The default catches premise numbers and pincodes and deliberately
  leaves localities alone; a street address written without a premise keyword is missed.
  `--address-clauses` trades that for a rule that also removes ordinary text.
- `--check` re-scans the output for structured identifiers. It cannot find a missed **name**.
- A 12-digit account number beginning `91` followed by 6–9 reads as a phone. Both readings redact
  the value; only the category label differs.
- Timestamps are preserved in full, as you asked. Exact timestamps plus message content are
  re-identifying in combination, so the output stays as sensitive as the input in that respect —
  which is why `data/scrubbed/` is gitignored too.
