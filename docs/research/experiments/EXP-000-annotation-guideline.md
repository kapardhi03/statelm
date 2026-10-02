# EXP-000 annotation guideline

**DRAFT, Kapardhi to edit and approve.** Do not label anything from this version.

Status: Draft · Drafted by Claude Code, 2026-10-02 · For EXP-000 (label feasibility)

This is the one document that defines the labels, so it is also the one document that decides
what EXP-000's κ means. A disagreement caused by a vague guideline is indistinguishable, in the
numbers, from a disagreement caused by a taxonomy humans cannot apply. The first would be my
fault; only the second is a finding. That is why the three open questions in §3 matter more than
anything else here.

**Every example below is invented.** No client conversation was read, requested or consulted in
writing this.

## 1. What this rests on, and what that means

The labels come from **ADR-003, which is Proposed, not Accepted**, and D4 (accept / modify /
reject it) is pending. EXP-000 is the experiment that tests ADR-003's assumption that "humans can
reliably distinguish the three abstention types". So this guideline is provisional on a taxonomy
it is being used to evaluate, which is normal for a feasibility study and worth stating plainly:
if the types collapse in practice, that is a result about the taxonomy, not a failure of
annotation.

**HEDGED follows rule (a)**, Kapardhi's decision of 2026-10-02: HEDGED records the tentative
value in the `value` column. `research-question.md` lists hedged statements as **Unresolved**
("tentative value or abstain?"); rule (a) fixes an operational rule so annotation can proceed and
does not resolve that question.

One item is one `(field, turn)` pair. You will see the turn and up to six preceding turns of
context. The five pilot fields are `budget` (numeric range), `property_type` (categorical),
`location_preference` (free text), `timeline` (temporal) and `decision_maker` (entity).

## 2. The six labels

Fill `value` only for VALUE and HEDGED. Use `notes` freely, especially when you label something
you think the guideline handles badly.

### NO-OP — this turn says nothing about this field
Not an abstention. Excluded from abstention metrics (ADR-003).

| Field | Turn | Why |
|---|---|---|
| `budget` | "Can you send the floor plan for tower B?" | The turn never engages budget. |
| `decision_maker` | "The photos look good, thanks." | Nothing about who decides. |

### VALUE — a value for this field is determinable from this turn
Put it in `value`, in the speaker's own terms.

| Field | Turn | `value` |
|---|---|---|
| `budget` | "My limit is 85 lakhs, that's firm." | 85 lakhs |
| `property_type` | "We only want a villa, not a flat." | villa |

### ABSTAIN:insufficient — the field is addressed, but no value of its type is recoverable
The turn engages the field. There is simply not enough to fill it.

| Field | Turn | Why |
|---|---|---|
| `budget` | "Budget is whatever it takes for the right place." | Budget is addressed; no figure exists to record. |
| `timeline` | "We need to move soon." | A temporal field, addressed, with no date or window. "Soon" is vague rather than tentative, which is what separates this from HEDGED. |

### ABSTAIN:ambiguous — the evidence supports several readings
Not that the speaker is unsure: that *you* cannot tell which value is meant.

| Field | Turn | Why |
|---|---|---|
| `budget` | "Around 40, I think." (no unit anywhere in the context) | 40 lakhs or 40 thousand. Two readings, orders of magnitude apart. |
| `location_preference` | "Somewhere near the new metro line." (the context has mentioned two different lines) | Two referents, both live. |

### ABSTAIN:conflicting — incompatible evidence, with no explicit correction
If the speaker corrects themselves ("sorry, I meant 90"), that is not conflicting: the later
value wins and the label is VALUE.

| Field | Turn and context | Why |
|---|---|---|
| `budget` | Context: "our max is 60 lakhs." Turn: "We've been approved for 90 and we'll use all of it." | Both stand; neither is withdrawn. |
| `decision_maker` | Context: "I decide this myself." Turn: "My brother has to sign off on it." | Incompatible, with no retraction. |

### HEDGED — a determinate value, held tentatively
Rule (a): record the tentative value in `value`.

| Field | Turn | `value` |
|---|---|---|
| `budget` | "Might stretch to 45 lakhs if the view is good." | 45 lakhs |
| `timeline` | "Probably by Diwali, but don't hold me to it." | Diwali |

## 3. Three questions this draft cannot answer

Each one changes labels on real items, so each is Kapardhi's. My proposal is given so there is
something to accept or reject, not because the choice is mine.

### Q1. HEDGED and ABSTAIN:ambiguous overlap in the source documents
`research-question.md` gives **"around 40"** as the example of ABSTAIN:ambiguous and
**"might stretch to 45"** as the hedged case. Under rule (a) both produce a tentative value, and
both are hedged in ordinary English. As written, an annotator can justify either label for
either turn.

What actually differs between the two documented examples is the **unit**: "around 40" has none,
so the value has several readings; "45 lakhs" has one, so the value is determinate and only the
speaker's commitment is soft.

**Proposed rule: ask what is uncertain.** Uncertainty about *which value* (unit, referent,
scope) is ABSTAIN:ambiguous. A determinate value held with uncertain *commitment* is HEDGED.
Under this rule "around 40 lakhs" is HEDGED with value 40 lakhs, and bare "around 40" is
ABSTAIN:ambiguous.

This boundary carries more weight than it looks. The sampler's hedge quota is 25% of sampled
turns, and its cue list includes "around", "maybe", "might" and "probably", so a large share of
items will sit near this line by construction. Leaving it implicit would depress κ for a reason
that is this document's fault, and D4 would be decided on it.

### Q2. Is the label about the turn, or about the field's state after the turn?
These diverge constantly. If the context already established `budget = 60 lakhs` and the turn is
"can you send the floor plan?", then *this turn* does nothing for budget (NO-OP) while the
field's state is perfectly well known (VALUE, 60 lakhs).

ABSTAIN:conflicting forces part of the answer: incompatible evidence almost always spans turns,
so the context must count for at least that label.

**Proposed rule: the label describes what this turn does to this field.** The research question
is about "turn-level state-delta operations", so NO-OP means this turn contributes nothing even
when the value is known from context, and conflicting means this turn introduces evidence
incompatible with the context. The context is there to interpret the turn, not to be labelled
itself.

### Q3. Does an agent's or the bot's restatement count as evidence?
The field descriptions say things like "what the customer has said they are willing to pay". If
the agent says "so your budget is 40 lakhs, correct?" and the customer does not answer in that
turn, is the `budget` item VALUE, ABSTAIN:insufficient, or NO-OP?

**Proposed rule: only the customer's own statements establish a customer field.** An agent's
restatement is NO-OP for that field until the customer confirms it. The alternative, treating a
confirmed restatement as VALUE, needs a definition of confirmation that this draft does not have.

## 4. How to work

- **Label independently.** No discussion with the other annotator while labelling, on any item,
  including the ones you are unsure about. That is what EXP-000 measures.
- **Do not change earlier labels** after a later item teaches you something. Note it instead.
  Revising silently makes agreement look better than the guideline earned.
- **One label per item.** If two fit equally, pick one and say so in `notes`. A tie recorded in
  `notes` is data about this document; a coin flip left unrecorded is noise in the κ.
- **Nothing you read is a model output or a label.** The sheets carry the conversation text, the
  field's name, type and description, and three empty columns for you to fill. If you see a
  suggested label, a confidence, or any mark on an item anywhere, stop and report it: the sheets
  are built to contain none, and one appearing would be a bug.

## 5. What a disagreement means here

EXP-000's working threshold is κ ≥ 0.6 per abstention type. A type below it has three possible
causes and they are not interchangeable: this guideline is unclear, the type does not survive
contact with real conversations, or the sample was too thin to say. The agreement script reports
the third directly, by marking any category under ten items as not interpretable. Separating the
first two is what the disagreement list is for, and it is why `notes` is worth filling in.
