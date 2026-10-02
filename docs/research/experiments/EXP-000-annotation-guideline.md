# EXP-000 annotation guideline

**APPROVED by Kapardhi, 2026-10-02.** This is the version to label from.

Status: Approved · For EXP-000 (label feasibility) · Design: inter-annotator, two annotators

Approval covers this text as the labelling instrument. It is not acceptance of ADR-003: that
ADR is still **Proposed**, D4 is still pending, and EXP-000 is the experiment that tests it.
See §1.

This is the one document that defines the labels, so it is also the one document that decides
what EXP-000's κ means. A disagreement caused by a vague guideline is indistinguishable, in the
numbers, from a disagreement caused by a taxonomy humans cannot apply. Only the second is a
finding. That is why §3 exists.

**Every example below is invented.** No client conversation was read or consulted in writing it.

## 1. What this rests on

The labels come from **ADR-003, which is Proposed, not Accepted**, and D4 is pending. EXP-000
tests ADR-003's own assumption that "humans can reliably distinguish the three abstention types",
so this guideline is provisional on a taxonomy it is being used to evaluate. If the types
collapse in practice, that is a result about the taxonomy, not a failure of annotation.

**HEDGED follows rule (a)** (Kapardhi's decision, 2026-10-02): HEDGED records the tentative value
in the `value` column. `research-question.md` lists hedged statements as **Unresolved**; rule (a)
fixes an operational rule so annotation can proceed and does not resolve that question.

One item is one `(field, turn)` pair. You see the turn and up to six preceding turns of context.
The five pilot fields are `budget` (numeric range), `property_type` (categorical),
`location_preference` (free text), `timeline` (temporal) and `decision_maker` (entity).

## 2. The six labels

Fill `value` for VALUE and HEDGED. Leave it empty otherwise. Use `notes` freely, especially when
you label something you think this document handles badly.

| Label | Means | `value` |
|---|---|---|
| **NO-OP** | This turn contributes nothing about this field. Not an abstention; excluded from abstention metrics (ADR-003). | empty |
| **VALUE** | One reading, stated. Includes approximations and ranges. | the value |
| **HEDGED** | One reading, but the customer is not committed to it. | the tentative value |
| **ABSTAIN:insufficient** | The field is addressed; no value of its type is recoverable. | empty |
| **ABSTAIN:ambiguous** | Two careful readers could write different values. | empty |
| **ABSTAIN:conflicting** | Incompatible evidence, with no explicit correction. | empty |

## 3. The boundaries

All three rules below are **Kapardhi's decisions, 2026-10-02**.

### 3.1 VALUE, HEDGED and ABSTAIN:ambiguous — three bins, one test each

- **VALUE** — one reading, stated, *including approximations and ranges*.
- **HEDGED** — one reading, but the customer is not committed to it.
- **ABSTAIN:ambiguous** — two careful readers could write different values.

**Approximation words alone ("around", "approximately") never make a turn HEDGED.** An
approximation is part of the value. Tentativeness is about commitment.

| Field | Turn | Label | `value` | Which test |
|---|---|---|---|---|
| `budget` | "Around 40 lakhs." | VALUE | `~40 lakhs` | one reading, stated |
| `budget` | "40 to 45 lakhs." | VALUE | `40-45 lakhs` | one reading, stated |
| `budget` | "Might stretch to 45." | HEDGED | `45` | one reading, not committed |
| `property_type` | "Maybe 3BHK." | HEDGED | `3BHK` | one reading, not committed |
| `budget` | "Around 40." (no unit anywhere in the context) | ABSTAIN:ambiguous | empty | 40 lakhs or 40 thousand: two readers, two values |
| `location_preference` | "Near the new metro line." (two different lines are live in the context) | ABSTAIN:ambiguous | empty | two referents, two values |

**On each side of the VALUE / HEDGED line:** "Around 40 lakhs" is VALUE because the approximation
is the value; "Might stretch to 45" is HEDGED because 45 is clear and the commitment is not.

**On each side of the VALUE / ambiguous line:** "Around 40 lakhs" is VALUE because both readers
write `~40 lakhs`; "Around 40" is ambiguous because one may write 40 lakhs and the other 40
thousand. The word "around" is identical in both. The unit is what differs.

### 3.2 A label describes what *this turn* contributes

Earlier mentions do not carry forward. A turn that adds nothing about a field is **NO-OP** for
that field, even when the field's value is perfectly well known from the context.

| Field | Context | Turn | Label |
|---|---|---|---|
| `budget` | "Our max is 60 lakhs." | "Can you send the floor plan for tower B?" | NO-OP |
| `budget` | "Can you send the floor plan?" | "Our max is 60 lakhs." | VALUE `60 lakhs` |

The same two turns, in either order: each is labelled for what it does, not for what is known by
the time it arrives.

### 3.3 Seller-side turns never establish a customer field

An `agent` turn does not establish a customer field, however clearly it states one. The
customer's confirmation does.

| Field | Speaker | Turn | Label | `value` |
|---|---|---|---|---|
| `budget` | agent | "So your budget is 50 lakhs?" | NO-OP | empty |
| `budget` | customer | "Yes." (following the turn above) | VALUE | `50 lakhs` |

This is the one place a value comes from outside the turn's own words. It does not contradict
§3.2: the confirmation is this turn's contribution, and the value it contributes is the one being
confirmed. §3.2 forbids carrying an earlier *customer* statement forward onto a later turn; it
does not forbid a turn whose whole content is agreement.

### 3.4 The remaining boundaries

| Boundary | One side | The other |
|---|---|---|
| NO-OP vs **insufficient** | `budget`, "Can you send the floor plan?" → **NO-OP**: budget is not engaged | `budget`, "Budget is whatever it takes for the right place." → **insufficient**: engaged, no figure exists |
| **insufficient** vs **ambiguous** | `timeline`, "We need to move soon." → **insufficient**: vague, but there is no competing reading to choose between | `timeline`, "By the end of the quarter." (the context has discussed both the financial and the calendar quarter) → **ambiguous**: two readers, two dates |
| **conflicting** vs VALUE | `budget`, context "our max is 60 lakhs", turn "We've been approved for 90 and we'll use all of it." → **conflicting**: both stand, neither withdrawn | `budget`, context "our max is 60 lakhs", turn "Sorry, I meant 90." → **VALUE** `90`: an explicit correction, so the later value wins |
| **conflicting** on an entity | `decision_maker`, context "I decide this myself", turn "My brother has to sign off." → **conflicting** | `decision_maker`, context "I decide this myself", turn "Actually my brother decides, ignore what I said." → **VALUE** `brother` |

## 4. Annotator instructions

You are **Annotator A** or **Annotator B**. Your sheet is `sheet_A.csv` or `sheet_B.csv`.

- **Label independently.** Do not discuss any item with the other annotator until **both** sheets
  are complete. Not the hard ones, not the ones you are sure about, not in passing. Agreement
  reached by discussion is not the thing EXP-000 measures.
- **Do not look at the other sheet**, before, during or after your own.
- **Your sheets are in different orders.** The two sheets hold the same items, each shuffled
  with its own seed, so neither of you can anchor on the other's sequence. Item ids are what
  pairs them up, not row numbers, so do not try to align the two by position.
- **One label per item.** If two fit equally, pick one and say so in `notes`. A tie recorded in
  `notes` is evidence about this document. A coin flip left unrecorded is noise in the κ.
- **Do not go back and change earlier labels** after a later item teaches you something. Note it
  instead. Revising silently makes agreement look better than this guideline earned.
- **Nothing in your sheet is a model output or a suggested label.** It holds the conversation
  text, the field's name, type and description, and three empty columns. If you see a suggested
  label, a confidence, or any mark on an item, stop and report it: the sheets are built to carry
  none, and one appearing is a bug.
- **A `[media: ...]` marker is not a redaction.** `[media: voice note]` means the message was a
  voice note whose content was never extracted. `[PERSON_1]`-style tokens are redactions. Both
  mean you cannot see the content; they differ in why.

## 5. What a disagreement means here

The working threshold is κ ≥ 0.6 per abstention type. A type below it has three possible causes,
and they are not interchangeable: this guideline is unclear, the type does not survive contact
with real conversations, or the sample was too thin to say. The agreement script reports the third
directly, marking any category under ten items as not interpretable. Separating the first two is
what the disagreement list and your `notes` are for.

## Change log

- **2026-10-02** — Drafted. Three boundary questions raised unresolved (VALUE/HEDGED/ambiguous,
  turn versus cumulative state, seller-side restatements).
- **2026-10-02** — All three settled by Kapardhi and recorded in §3. The VALUE/HEDGED/ambiguous
  split became three bins with one test each, replacing the drafted proposal, which had made
  "around 40 lakhs" HEDGED; it is VALUE `~40 lakhs`. Examples restructured so every boundary has
  one example on each side.
- **2026-10-02** — Annotator instructions added (§4) for the inter-annotator design: two
  annotators, A and B, independent labelling, no discussion until both sheets are complete,
  per-sheet shuffled item order.
- **2026-10-02** — Note on the sampler's enrichment: its hedge cues ("around", "maybe", "might")
  now enrich for **both** VALUE-with-approximation and HEDGED, since "around" no longer implies
  HEDGED. This is intended. The cues decide only what is sampled and never appear in a sheet.
- **2026-10-02** — Consequence for the agreement script, recorded here because it follows from
  §3.1 rather than from any decision about metrics: because approximations are now VALUEs, the
  value-agreement comparison treats an approximation marker as part of the value.
  `~40 lakhs` and `around 40 lakhs` are the same value; neither is `40 lakhs`.
- **2026-10-02** — Sheet order: the shuffled unit is the turn block, not the item, so a turn's
  five fields stay together. §4 says so to the annotators.
- **2026-10-02** — **Approved by Kapardhi.** DRAFT marker removed; this text is the labelling
  instrument for EXP-000. Any later change to a label definition needs a new entry here and,
  if labelling has begun, a decision about the items already labelled under the old wording.
  ADR-003 remains Proposed and D4 remains pending: approving this guideline settles how the
  labels are applied, not whether the taxonomy is right.
