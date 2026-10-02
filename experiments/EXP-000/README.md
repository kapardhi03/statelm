# EXP-000 local data tools

Three scripts, all run **on your machine, never in a Claude session**:

- `extract.py` pulls conversations out of the ARTHRYX PostgreSQL database into
  `data/raw/arthryx_messages.csv`.
- `scrub.py` turns that CSV (or any CSV / XLSX / JSON export) into scrubbed JSONL, plus two
  reports.
- `sample_items.py` samples annotation items from the scrubbed JSONL and writes one annotation
  sheet per annotator, with empty label columns.

Claude never connects to the database and never sees message content.

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

## The run order

```bash
cd experiments/EXP-000
uv sync

# 1. Look at the schema. Prints table, column, type and row count. No row values.
uv run python extract.py --inspect

# 2. Copy extract.example.yaml to extract.yaml and fill in the mapping from that output.
#    Paste the --inspect output into the Claude session and the mapping can be written for you.

# 3. Pull the conversations.
uv run python extract.py --extract --config extract.yaml

# 4. Scrub them. columns.yaml already matches step 3's CSV, so no edits are needed.
uv run python scrub.py --input ../../data/raw --output ../../data/scrubbed/EXP-000 \
                       --columns columns.yaml --check

# 5. Sample the annotation items. fields.yaml holds the five pilot fields already.
uv run python sample_items.py --input ../../data/scrubbed/EXP-000 \
                              --output ../../data/scrubbed/EXP-000/annotation \
                              --fields fields.yaml --n-items 80 --seed 0

# 6. The annotators fill the label / value / notes columns. Then measure agreement.
uv run python agreement.py --sheets sheet_annotator_1.csv sheet_annotator_2.csv
```

## extract.py: pulling conversations out of PostgreSQL

### DATABASE_URL, ideally for a read-only user

Credentials come from the `DATABASE_URL` environment variable and **nowhere else**. No file in
the repo is consulted, nothing is hardcoded, and the URL is never printed, logged or written to
any output. `extract.py` writes no run config at all, so there is nothing that could record it.

Create a user that cannot write even if something goes wrong:

```sql
CREATE ROLE statelm_ro LOGIN PASSWORD 'choose-something-long';
GRANT CONNECT ON DATABASE arthryx TO statelm_ro;
GRANT USAGE ON SCHEMA public TO statelm_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO statelm_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO statelm_ro;
ALTER ROLE statelm_ro SET default_transaction_read_only = on;
```

Then export it for that shell only, not in a file:

```bash
export DATABASE_URL='postgresql://statelm_ro:choose-something-long@localhost:5432/arthryx'
```

A read-only role is defence in depth, not the only defence: the script also sets
`default_transaction_read_only = on` as its first statement and refuses to issue anything that is
not a `SELECT`.

### `--inspect`

Prints `schema.table (n rows)` and each column with its type, for tables whose name or column
shape looks conversational. `--all-tables` widens it when the heuristic misses yours.

It **cannot** print a row value, and not because of a filter: in this mode no statement selects a
column from a user table. The only queries are against `information_schema` and `count(*)`. A test
asserts exactly that over every statement the mode issues, which is why the output is safe to
paste into a Claude session.

### `--extract --config extract.yaml`

Writes `data/raw/arthryx_messages.csv` with exactly five columns —
`conversation_id, speaker, speaker_role, timestamp, text` — one row per message, ordered by
conversation then timestamp. Terminal output is counts only: conversations, messages, per-role
counts, date range.

| Option | Default | What it does |
|---|---|---|
| `--n-conversations` | 100 | How many conversations to sample |
| `--seed` | 0 | Seeds the sampling |
| `--min-customer-messages` | 4 | Skips trivial one-line chats |
| `--since` / `--until` | none | Inclusive lower, exclusive upper bound on timestamp |
| `--output` | `arthryx_messages.csv` | Relative to `data/raw/`; anywhere else is refused |

Sampling happens **in Python** with `random.Random(seed)`, not with SQL `ORDER BY random()`, so the
same seed selects the same conversations across runs and server versions. That matters because
EXP-000's pilot items have to be identifiable later and kept out of the eventual test split.

`extract.yaml` takes a list of `sources`, each naming one table and mapping the five fields, with
an optional `role_map` onto `bot` / `agent` / `customer`. Several same-shaped tables can be listed
and are merged in order. **For data spread across joined tables, make a view in PostgreSQL and
point at the view** — a join DSL in YAML would be a worse config language and a much larger SQL
surface to audit.

A mapped column that does not exist is an error naming it and listing what is available. Nothing
is guessed. Identifiers in the SQL are the catalog's own spelling, looked up before use, so a value
from the config never reaches the query as free text.

### What the extractor guarantees, each covered by a test

1. **Read-only.** `SET default_transaction_read_only = on` is the first statement on the
   connection, and the driver's own read-only flag is set too.
2. **SELECT only.** Every later statement goes through a gate that raises on anything else.
3. **No row values anywhere but the CSV.** Messages stream from a cursor straight into the CSV
   writer; no function in the extract path returns or accumulates message text.
4. **Writes only to `data/raw/`.** Any other output path is refused before a connection is used.
5. **Credentials from `DATABASE_URL` only**, never from a repo file, never printed. A test asserts
   a password-bearing URL appears nowhere in the output.

## What this is, and what it is not

It is a **first-pass redactor that makes your spot-check tractable.** It is **not** a guarantee of
de-identification.

Structured identifiers (emails, phones, UPI, IFSC, cards, account numbers, transaction
references) are caught reliably. Names are caught **only when they appear in the export's own
speaker roster** — a third party named in passing is not detected. Addresses are the weakest
category by a distance. The audit report exists precisely because you have to be the final check.

## scrub.py: install and run

`columns.yaml` is committed and already matches `extract.py`'s CSV. Only edit it, or copy
`columns.example.yaml`, if you are scrubbing some other export.

```bash
cd experiments/EXP-000
uv sync                      # PyYAML, openpyxl, psycopg; pytest for the tests
uv run pytest                # 216 tests, all on fabricated data, no network, no database

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

## sample_items.py: items and annotation sheets

Reads the scrubbed JSONL, samples turns, and writes one sheet per annotator with the `label`,
`value` and `notes` columns **empty**. Runs on your machine, like everything else here: it reads
conversation text, so it never runs in a Claude session.

```bash
uv run python sample_items.py --input ../../data/scrubbed/EXP-000 \
                              --output ../../data/scrubbed/EXP-000/annotation \
                              --fields fields.yaml --n-items 80 --seed 0
```

| Option | Default | What it does |
|---|---|---|
| `--fields` | required | `fields.yaml`; no fallback, see below |
| `--n-items` | 80 | Target `(field, turn)` items, trimmed down to a whole number of turns |
| `--seed` | 0 | Seeds both the quota draws and the random top-up |
| `--context-turns` | 6 | Preceding turns shown with each item |
| `--annotators` | `annotator_1,annotator_2` | One identical sheet per name |

### `fields.yaml`: the five pilot fields

One item is a `(field, turn)` pair, so the sampler cannot run without knowing which fields are
being tracked, and there is no agreed field list in `docs/research/` because Stage 3 (data model)
has not started. Kapardhi settled a pilot list on 2026-10-02 and it is committed as
`fields.yaml`: `budget`, `property_type`, `location_preference`, `timeline`, `decision_maker`.

Its header says what it is: **a pilot field list, not the StateLM data model.** Nothing
downstream should read it as a schema proposal. `fields.example.yaml` stays as the template if you
ever want a different list; `--fields` is still required, with no fallback, so a run always names
the list it used.

The field count multiplies the turn count: five fields and `--n-items 80` gives 16 turns.

### Two rules from the experiment record, and how the code keeps them

**1. No pre-labelling, no suggested labels, no acting as an annotator.**

Turns are sampled with cue lists (`cues.py`) that look for corrections ("actually", "I meant"),
hedges ("around", "depends", "might") and stretches with three or more distinct speakers. Those
cues decide what gets *sampled*. They never reach the sheet. An annotator who could see that a
turn "matched a hedge cue" would be primed toward HEDGED, so the stratum that caused a turn to be
drawn is written to `manifest.json`, which the researcher reads and annotators do not. The
manifest carries a `do_not_show_to_annotators` key saying exactly that.

Four tests hold the line: the label columns are empty in every row, the header is exactly
`SHEET_COLUMNS` with no stratum or cue column, no string from the label vocabulary appears
anywhere in the sheet file, and the words "hedge" and "stratum" do not either.

Precision of the cue lists therefore does not matter much. A false match costs a slightly less
enriched sample; it cannot corrupt a label.

**2. Pilot items must not enter the eventual test split.**

`pilot_items.json` records every sampled turn by conversation id and turn index, ids only, no
text, so these turns can be excluded when the real splits are frozen.

### Enrichment quotas are targets, not guarantees

Defaults: 25% corrections, 25% hedges, 20% multi-speaker, the rest drawn at random. Each quota is
filled first, then the sample is topped up randomly.

A corpus with few corrections cannot be made to have more. When a quota cannot be filled the
shortfall is **printed and written to the manifest**, never silently absorbed, because an
under-enriched sample changes what EXP-000's agreement numbers mean.

### What it writes

```
<output>/
  sheet_annotator_1.csv       identical sheets, empty label columns
  sheet_annotator_2.csv
  manifest.json               settings, enrichment report, per-turn strata. RESEARCHER ONLY.
  pilot_items.json            sampled turn ids, for test-split exclusion
  labels_reference.txt        the label vocabulary
```

`labels_reference.txt` is the vocabulary only. The annotation **guideline** is a human document
that you write and approve; the file says so, and says to label nothing without it.

### Two interpretations you should check

- **"Multi-speaker turn"** is read as *a turn whose context window holds three or more distinct
  speakers*, since a turn has exactly one speaker of its own. The record does not define it.
- **Items trim on a turn boundary**, so `--n-items 80` with 4 fields gives exactly 20 turns and
  no turn is half-labelled. The alternative, cutting mid-turn to hit 80 exactly, would ask an
  annotator about some fields of a turn and not others.

Passing a single `--annotators` name works and prints a reminder of what the record says the
fallback then is: intra-annotator agreement, relabelled after at least a week, blind to the first
labels, and reported as intra-, not inter-annotator. Whether there is a second annotator is D3,
still open, and not something this script settles.

### The same two guarantees as the scrubber, each under test

It reads client text, so it carries them too: it **makes no network call**, and it **never
modifies the input** (the scrubbed tree is hashed before and after a full run). Writes go through
the same containment check, and an output directory nested inside the input is refused.

### Limits

- Sampling is over turns, not conversations, so one talkative conversation can contribute several
  items. With `--n-items 80` and a 100-conversation corpus that is unlikely to matter; with a
  small corpus, check the manifest's `turn_strata` for clustering.
- A turn with no text is skipped. A turn whose *context* is empty (the first turn of a
  conversation) is not, and arguably should be judged as insufficient-information rather than
  sampled; that is a guideline question, not a sampler one.
- The cue lists are English and Indian-English only, and they are literal substrings. A
  correction phrased without a cue word is sampled only by the random top-up.
