# Research Question (v1, proposed)

## Primary question

> Given a natural-language schema not observed during training, can a ≤4B-parameter model
> produce turn-level state-delta operations whose values, supersession links, and abstentions
> match human judgment, within δ of a frontier model, and does that performance hold as schema
> novelty, conversation length, and revision count increase?

Sales/CRM is the first application. It is not the research problem.

## Formal statement (claim shape, not losses)

```text
Schema    S = {(f_i, type_i, desc_i)}
Input     X_t = (H_1..t, timestamps, S, Z_{t-1})
Output    Ŷ_t = {(field, op, value, evidence, confidence)}
          op ∈ {ADD, UPDATE, RETRACT, ABSTAIN_k}
State     Z_t = Apply(Z_{t-1}, Ŷ_t)        # deterministic, not learned (ADR-002)

Claim     for novelty level n ∈ {L0..L5}:
          Q_small(n) ≥ Q_frontier(n) − δ
          Q = (value acc., stale-value rate, selective risk, evidence acc.)

H-A       |d AbstentionQuality/dn| > |d ValueAccuracy/dn|
```

δ is not yet set. Setting it is a Stage 4 (benchmark) decision.

## Interaction hypotheses (the actual research claim)

The conjunction of capabilities is not a contribution by itself. The claim rests on these:

- **H-A (schema × abstention):** abstention quality degrades faster under schema novelty than
  value accuracy does. Models become confidently wrong on unfamiliar fields.
- **H-B (schema × temporal):** stale-value errors increase with schema novelty, because binding a
  correction to an unfamiliar field is harder.
- **H-C (scale):** there is a measurable size threshold below which the joint task collapses even
  when single capabilities survive.

If none hold, the honest finding is "difficulty is additive": a benchmark paper, not a model paper.

## Operational definitions

### "Small, self-hostable" (D1 decided 2026-10-09; primary size changed 2026-10-10)
**Primary: ~9B, `Qwen/Qwen3.5-9B`.** Size curve at ~1B / ~4B / ~8B, as decided.
Reason: FnCTOD and LDST already cover 7–13B.

**Primary size changed on Kapardhi's instruction, 2026-10-10.** Transcribed from Kapardhi,
2026-10-10, verbatim: "9B becomes the new primary". Previously: "Proposed: ≤4B parameters, runs
quantized on one consumer GPU. Size curve at ~1B / ~4B / ~8B. Reason: FnCTOD and LDST already
cover 7–13B", decided as D1 on 2026-10-09.

**His instruction named the primary size and nothing else, so nothing else here has been
changed.** The size curve, the "runs quantized on one consumer GPU" clause and the Reason sentence
stand exactly as D1 decided them. A first version of this edit, in commit `5ed50fb`, also
rewrote the curve to "~4B / ~9B" and gave a reason for dropping the ~1B point; that went beyond
his instruction and beyond what Claude Code may change, and it is reverted here.
*Recorded by Claude Code, 2026-10-10, after a `research-reviewer` pass caught it.*

*Flagged by Claude Code, not part of his instruction. Five consequences, none of them resolved
here, all of them his:*
1. **A 9B primary contradicts a `literature.md` row.** Line 11, the FnCTOD row, has as its
   consequence column: "Small-ish models doing DST is not novel. **Our size range must go below
   7B**". `literature.md` line 3 is the rule "no claim of novelty may contradict a row below". A
   ~9B primary contradicts that row, and the row is left unannotated because `literature.md` is
   his. So a contribution resting on model size is not available at the primary size.
2. **The primary question at the top of this file** still reads "can a **≤4B-parameter** model…",
   and now disagrees with the primary size.
3. **Contribution 3 below** still reads "open ≤4B model and recipe" (line 103).
4. **`knowns-unknowns.md`** still asks "Where on 1B / 4B / 8B does the joint task collapse?", and
   **`STATE.md`** still records D1 as "≤4B primary, size curve at ~1B / ~4B / ~8B, as proposed"
   with "Last updated: 2026-10-09". `STATE.md`'s "Decisions pending" section is his to edit and
   has not been touched.
5. **H-C** is "a measurable size threshold below which the joint task collapses". The decided
   curve has three points and keeps one below the 7B band; running fewer than three, or dropping
   the ~1B point, would leave no point below that band and no way to locate a threshold. No ~1B
   model is currently offered by Tinker (per its published `models.json`, fetched 2026-10-10;
   Qwen3 0.6B / 1.7B and all Llama models retired 2026-06-12), so that point needs separate
   infrastructure. That is a constraint on how the curve gets run, not a change to it.

Detail and cost figures in `plan-2026-10-10-modelling-track.md` §6.

### "Unseen schema": novelty ladder
Report lexical overlap and embedding similarity to the nearest training field for every test item.

| Level | What is new | Example |
|---|---|---|
| L0 | Nothing (seen schema) | Control |
| L1 | Surface only: renamed or redescribed | `budget` → `cust_bdgt_max` |
| L2 | New field, seen domain | `parking_requirement` never trained |
| L3 | New value semantics | Ranges, multi-valued, conditional |
| L4 | New domain | Train real estate, test insurance |
| L5 | Seen fields in unseen combinations | Compositional |

### "Abstain" (ADR-003, proposed)
- **NO-OP:** no relevant evidence this turn. Not abstention. Excluded from abstention metrics.
- **ABSTAIN:insufficient:** field addressed, value underspecified for its type.
- **ABSTAIN:ambiguous:** several readings ("around 40", lakhs or thousands?).
- **ABSTAIN:conflicting:** incompatible evidence, no explicit correction.
- **Unresolved:** hedged statements ("might stretch to 45"). Tentative value or abstain?
  EXP-000 uses rule (a) provisionally, pending its results: HEDGED records the tentative
  value in the value column ("might stretch to 45" -> label HEDGED, value 45). Kapardhi's
  instruction, 2026-10-02. This fixes an operational rule so annotation can proceed; it
  does not resolve the question.

### "Over time"
Two separate capabilities:
1. Current-state correctness after revisions (stale-value rate).
2. Lineage correctness (which op superseded which).

Historical queries are derived from the ledger, never generated by the model.

## Contributions (most to least defensible)
1. **Benchmark:** schema-conditioned, long-horizon state tracking with a controlled novelty ladder,
   typed abstention with measured human agreement, gold supersession and evidence.
2. **Empirical findings:** H-A, H-B, H-C.
3. **Model:** open ≤4B model and recipe. Research value only if ablations explain why it works.

## Explicit non-contributions
- State-delta / operation formulation (SOM-DST 2020, MemOps 2026)
- Schema-in-prompt zero-shot state tracking (SGD, FnCTOD, LDST)
- "Small open models can do DST" (LDST, FnCTOD)
- Confidence estimation for DST (Sun et al. 2024)
- Guideline-following extraction on unseen schemas (GoLLIE)
- Memory lifecycle operations or long-horizon memory benchmarks
- CRM extraction as a product capability

## Open flags on the model contract (Stage 2)
- ABSTAIN does not change state. Separate channel or per-field status?
- CONFIRM changes certainty, not value. Needs a research question to justify v0.1 inclusion.
- `supersedes` must reference an op/version ID, not a value.
- Verbalized vs logprob confidence is an experimental question, not a format choice.
