# EXP-000 local data tools

Four scripts, all run **on your machine, never in a Claude session**:

- `extract.py` pulls conversations out of the ARTHRYX PostgreSQL database into
  `data/raw/arthryx_messages.csv`.
- `scrub.py` turns that CSV (or any CSV / XLSX / JSON export) into scrubbed JSONL, plus two
  reports.
- `sample_items.py` samples annotation items from the scrubbed JSONL and writes one annotation
  sheet per annotator, with empty label columns.
- `agreement.py` reads the filled sheets back and reports Cohen's kappa, a confusion matrix and
  value agreement against EXP-000's pre-registered threshold.

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
                              --fields fields.yaml --n-items 80 --seed 0 \
                              --annotators A B

# 6. Annotators A and B fill the label / value / notes columns. Then measure agreement.
uv run python agreement.py --sheets sheet_A.csv sheet_B.csv
```

Step 3 takes the role note and the tenant check for the ARTHRYX schema:

```bash
uv run python extract.py --extract --config extract.yaml \
    --tenant-column builder_id \
    --role-note "agent = seller side. Outbound includes the bot and any human takeover; this schema cannot distinguish them (meta is excluded)."
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

### `kinds:` — what happens to a non-text message

`public.messages` carries more than text: audio, image, video, document, contacts, unsupported,
sticker and reaction. Each kind needs exactly one disposition, and **a kind the config does not
classify fails the run** rather than being guessed at, because an unclassified kind may carry
content nobody has decided about.

```yaml
kinds:
  column: kind
  text: [text]
  placeholder:
    audio: "[media: voice note]"
    image: "[media: image]"
    video: "[media: video]"
    document: "[media: document]"
    unsupported: "[media: unsupported]"
    contacts: "[media: contact card]"
  drop: [reaction, sticker]
```

**The substitution happens in SQL, not Python.** The SELECT is a `CASE` over the kind column
that returns the body only for a text kind and a bound placeholder string otherwise, so a media
row's body is **never transmitted to this process at all**. "Never read or copy the original
body for these rows" is therefore a property of the query rather than a promise about what the
code does with a value it already holds. A test asserts it on the statements, not on the output:
asserting on the output would pass either way.

The `[media: ...]` form keeps these distinguishable from the scrubber's `[PERSON_1]`-style
tokens. Both mean the annotator cannot see the content; they differ in why, and the guideline
says so. A test runs the scrubber's detectors over every placeholder to confirm none of them
looks like PII.

An empty `body` on a **text** row is dropped as a non-message. A placeholder row legitimately has
no body, so the check is scoped to the text kinds.

### `exclude:` — columns that reach no statement

```yaml
exclude: [intent, meta, language, media_id, media_mime]
```

`intent` is a model prediction. Keeping it out is rule 3 of `CLAUDE.md`: a prediction sitting in
the same table as the text must not reach an annotator's sheet. `meta` is raw JSON and likely to
hold PII. `media_id` and `media_mime` identify content this extract deliberately does not take.

Enforced twice. A column that is both excluded and mapped is a **config error**, which catches
`text: intent`. And a test runs a full extract against the fake database and asserts none of the
excluded names appears in **any statement issued**, using the statement log the fake connection
keeps. That is a check on the SQL, not a promise about the mapping.

### Eligibility, and what `--min-customer-messages` counts

It counts **customer-role rows of a text kind**, nothing else. A conversation of four voice notes
has no labellable turns and must not pass a floor that exists to guarantee four. Outbound text
does not count either.

The filters and the floor are computed from one aggregate query, with the same `WHERE` clause the
extract uses. That matters: if the kind filter applied only to the extract, conversations would be
*selected* on counts including rows the extract then drops.

### Timestamps, and the ordering bug this closes

The extractor reads `created_at`'s type from `information_schema` rather than assuming it. A
temporal column sorts correctly as itself; a **text** column is cast with `::timestamptz`.

Without that cast there was a silent corruption waiting. The SQL said `ORDER BY conversation,
created_at` while `write_csv` merged the per-source streams with `heapq.merge` keyed on the
*parsed* ISO value, and `heapq.merge` assumes each input is already sorted by that key. With a
text column holding mixed formats, SQL sorts lexically, the merge assumes chronological, and the
CSV comes out misordered — and `turn_index` in the annotation items comes straight from this
order.

Three guards now, because the cast itself can only be verified against real PostgreSQL:

1. Every row's timestamp must parse. One that does not **fails the run**; previously it became
   an empty string and sorted to the front of its conversation.
2. Each stream is asserted non-decreasing in the merge key as it is consumed, so a disagreement
   between the SQL ordering and the Python key fails instead of writing a bad CSV.
3. A test forces that disagreement and checks the guard fires.

### `--tenant-column`: a check, not a filter

`builder_id` has one value in the ARTHRYX database, and EXP-000's consent assumption is
single-tenant. `--tenant-column builder_id` records the distinct values and their counts in the
metadata and **refuses the run if there is more than one**, rather than silently narrowing to one
tenant. If a second ever appears, that is a consent question, not a query to fix.

### The metadata sidecar

`--extract` writes `<output>.meta.json` beside the CSV: rows by kind, each kind's disposition,
placeholder counts per kind and the total, dropped counts, the role map and the role note
verbatim, the eligibility rule and how many conversations passed it, the timestamp column's
declared type and order expression, the excluded columns, the tenant values, and the seed.

Everything in it is an aggregate, so it is safe to copy into `runs/EXP-000/`. It lives in
`data/raw/` because that is the one tree this script may write, and it is gitignored with the CSV
it describes.

> It also found a bug on the way in. `scrub.py` scans `data/raw/` for `.csv`, `.xlsx` and
> `.json` inputs, so the new sidecar was picked up as a conversation export and the scrubber
> failed on it. The existing cross-tool test caught that immediately; `parsers.discover` now
> skips `*.meta.json`, with its own tests.

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
uv run pytest                # 399 tests, all on fabricated data, no network, no database

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
| `--annotators` | `A B` | One sheet per name, space- or comma-separated |

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

### Two annotators, two orders, one item set

EXP-000 is an inter-annotator design with two annotators named only **A** and **B**. No personal
name goes into a sheet, the manifest or any other annotation artifact; which person is which
letter is deliberately not recorded in this repository.

`--annotators A B` writes `sheet_A.csv` and `sheet_B.csv`. Both hold **the same items**, each in
**its own seeded order**, so neither annotator can anchor on the other's sequence and a
disagreement cannot be an artefact of both having read the items in the same run-up. The
per-annotator seed is derived from the run seed and the annotator's name, so one `--seed`
reproduces both orders, and adding a third annotator does not disturb A's or B's.

The orders are recorded in `manifest.json`. Items pair up by `item_id`, never by row, so
`agreement.py` is unaffected by the shuffle — and a test asserts that every number it reports is
byte-identical whether the sheets arrive shuffled or in order. With a single item no distinct
permutation exists; the run reports that rather than pretending.

One cost worth knowing: an item-level shuffle scatters a turn's five fields across the sheet, so
the annotator re-reads the same context up to five times and cannot tell that two items share a
turn. Shuffling whole turn blocks instead would meet the same goal more cheaply; this is
item-level because that is what was specified.

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
  sheet_A.csv                 the same items, in A's own seeded order, empty label columns
  sheet_B.csv                 the same items, in B's own seeded order
  manifest.json               settings, enrichment, per-turn strata, both sheet orders.
                              RESEARCHER ONLY.
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

## agreement.py: measuring the labels

Reads two filled sheets and reports Cohen's kappa overall and per category, a confusion matrix,
and value agreement, against the threshold pre-registered in EXP-000's record.

```bash
# two annotators
uv run python agreement.py --sheets sheet_annotator_1.csv sheet_annotator_2.csv

# or one annotator's two passes
uv run python agreement.py --passes pass_1.csv pass_2.csv
```

| Option | Default | What it does |
|---|---|---|
| `--sheets A B` | — | two annotators: **inter**-annotator agreement |
| `--passes A B` | — | one annotator twice: **intra**-annotator agreement |
| `--seed` | 0 | seeds the bootstrap |
| `--bootstrap` | 2000 | resamples per interval |
| `--allow-partial-overlap` | off | measure the shared items when the sheets differ, and record it |
| `--out-root` | `runs/EXP-000` | aggregates only |
| `--disagreements-dir` | `data/scrubbed/EXP-000` | must be inside `data/scrubbed/` |

### The mode is structural, not a flag

There is no `--mode` to set wrong and no default to fall back on: `--sheets` means inter, and
`--passes` means intra. The mode appears in `metrics.json`, `config.json`, the disagreement
file's header record and every printed line. Passing both, or neither, is refused.

With `--passes` the script also prints what it **cannot** check: the record requires the relabel
to come at least a week later and to be blind to the first labels, and neither is visible in a
CSV. Both are yours to guarantee, and the run says so rather than implying the fallback was
applied correctly.

### A thin category is reported, never hidden

Below ten items (`n_either`, the count of items *either* rater put in the category) a category
keeps its kappa and all four counts and is marked **not interpretable**. Nothing is dropped.

The consequence matters more than the rule: three items of `ABSTAIN:conflicting` that both
annotators agreed on perfectly give a kappa of 1.000, which looks like the best result in the
table. The script reports that kappa, marks it uninterpretable, and prints the hypothesis as
**CANNOT BE EVALUATED** rather than "not refuted". A pre-registered threshold applied to three
items is not evidence, and a run that quietly passed on one would be worse than a run that
failed.

### Where each kind of output goes

```
runs/EXP-000/<run-id>/
  metrics.json      kappas, intervals, counts, confusion matrix, verdict. AGGREGATES ONLY.
  config.json       commit, seed, sheet hashes, every pre-registered number

data/scrubbed/EXP-000/
  disagreements_<run-id>.jsonl    item ids, both labels, and both values for a value mismatch
```

The split is enforced, not just intended. `metrics.json` and `config.json` contain no item id,
no label per item and no value; a test plants a canary string in the sheets and asserts it
appears in neither file, and another asserts only those two files are written. The disagreement
list carries the per-item detail and the script **refuses** to write it outside
`data/scrubbed/`, which is gitignored.

Both values are included for a value mismatch because an item id alone cannot tell you whether
two annotators disagreed about the budget or just typed the same figure differently. That is
exactly why the file is confined to the gitignored tree.

### Value agreement, twice

Label agreement alone hides value disagreements: two annotators can both say VALUE on every item,
giving perfect label agreement, while disagreeing about half the values. So value agreement is
reported separately over the items **both** sheets labelled VALUE, under two normalizations:

| | What it sees past | "40-45 lakhs" vs "40 to 45 lakhs" |
|---|---|---|
| `strict` (primary) | case, whitespace, trailing punctuation | **different** |
| `number_aware` (secondary) | the above, plus magnitude words, currency marks, range connectives and Indian digit grouping | **same** |

Strict is the primary figure because it is a lower bound that cannot flatter the annotators.
Number-aware is reported beside it, never instead of it, so the gap between the two tells you how
much of your value disagreement is formatting. `80 lakhs` and `8000000` are the same number;
`around 40 lakhs` and `40 lakhs` are **not** collapsed, because HEDGED is a label of its own and
merging them would hide the thing EXP-000 is measuring.

### The intervals

Every kappa and both value figures carry a seeded percentile bootstrap 95% interval, computed
twice:

- **by conversation** (primary): whole conversations are resampled with replacement. This is the
  right unit because five fields times one turn means five items sharing one conversation's
  context, and items from one chat are not independent.
- **by item** (secondary): items resampled as if independent. Narrower, reported for comparison.

A replicate whose kappa is undefined, which happens when the category appears in neither rater's
column of that resample, is **excluded and counted**. Above 5% undefined the interval itself is
marked not interpretable, because it then describes only the resamples in which the category
happened to appear. An interval that is not interpretable prints with a `*`.

### What it will not do

It prints a verdict against the pre-registered threshold and stops there. It does not write to
the experiment record, and `metrics.json` says so in as many words: *"A verdict against a
pre-registered threshold is not a Result. Result, Interpretation and Decision in the experiment
record are a human's to fill."* A test hashes the record file before and after a run.

### The pre-registered numbers

All of them live in `thresholds.py`, each with its provenance, so they are auditable in one
place and diffable on their own: the κ ≥ 0.6 threshold and the three abstention types it applies
to (from the record), the ten-item floor, the bootstrap units and resample count, the undefined
replicate ceiling, the two value normalizations, and HEDGED rule (a). Kapardhi settled the
measurement choices on 2026-10-02, before any real run.

One of them is not a judgement call but a bug fix. A one-vs-rest table of (2 both-in, 1 a-only,
1 b-only, 14 both-out) has an exact kappa of 3/5, but computes as `0.5999999999999996` in binary
floating point, so a bare `kappa >= 0.6` would report BELOW on a category that exactly meets the
threshold. n = 18 is an ordinary size for a rare abstention type here, so this is reachable
rather than theoretical. `meets_threshold()` carries a 1e-9 tolerance and a test pins that exact
table, with an assertion that fails if the hazard ever disappears so the tolerance can be removed.

### Known limits

- A percentile bootstrap on 60-100 items with rare categories gives wide intervals, and
  percentile intervals are rougher than BCa. The ten-item floor is the main guard against
  over-reading a thin category; the interval is the second.
- `number_aware` compares the leftover words as a set, so a value whose meaning depends on word
  order is not protected. It is a secondary figure for that reason.
- Cohen's kappa is for exactly two raters. A third annotator would need Fleiss' kappa or
  Krippendorff's alpha, which this script does not implement.
