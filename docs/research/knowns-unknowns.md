# Knowns, Unknowns, Risks, Research Clusters

Rule: do not resolve an unknown by guessing. Move an item to Known only with an experiment ID
or a literature row as evidence.

## Known (with evidence)
- Schema-prompted DST is sensitive to schema wording (SGD-X)
- "Unseen" in SGD is leaky: most unseen slot names match train names (SGD-X)
- 7–13B open models reach ChatGPT-era DST (FnCTOD, LDST)
- Operation-level memory evaluation exists, without schemas (MemOps)
- Rare ops (DELETE) are much harder than UPDATE (SOM-DST)
- Ordered state-trajectory reconstruction is fragile even for strong models (MemOps)
- Real customer turns are state-sparse in this deployment (EXP-000 v2 census, 2026-10-03):
  of 135 eligible customer turns, 18 mention a tracked field (budget 10, property_type 3,
  location 3, decision_maker 2, timeline 1), and 0 matched a correction or hedge cue. 54 turns
  were voice-note placeholders. The corpus as it stands cannot support the abstention
  hypothesis.
- Kapardhi's romanized Telugu and Hindi cue forms matched 0 of 135 eligible customer turns
  (EXP-000 v3 census, 2026-10-03; the same corpus as v2, so not an independent sample):
  field_mention 18, correction 0, hedge 0, unchanged from v2. Transcribed from Kapardhi,
  2026-10-03, counts only. His reading, recorded as his: cue-language blindness does not
  explain the absence, which leaves genuine absence from the text channel and the 54 voice
  notes as the remaining explanations. What is measured here is a cue match, not a hedge.
- **Across all 286 customer text turns in this deployment, 22 mention a tracked field and 0
  match any hedge or correction cue. Script blindness and pipeline faults are ruled out.**
  Transcribed from Kapardhi, 2026-10-03; the ruling-out is his reading, recorded as his.
  EXP-000 runs: 135 eligible targets (18 field mentions) plus 151 turns below the 3-word floor
  (4 field mentions, run `20261003T164527Z-2773803`), and the two populations are exact
  complements by the sampler's own eligibility predicate, so 286 is every customer turn of real
  text in the corpus. The measurements his reading rests on: `ascii_only` 121 of 135 eligible
  targets with `telugu` 1, so the writing system was not blocking the probe; and field mentions
  and the amount pattern firing on both populations, so text is arriving and is matchable.
  What is measured is a cue match, not a hedge, and 0 cue matches across 286 turns is the
  largest-denominator form of that result rather than a new kind of evidence.

## Unknown (to test)
- Whether H-A / H-B / H-C hold
- Frontier headroom on this exact task (EXP-001)
- Human agreement on abstention types (EXP-000)
- Size threshold for the joint task
- How hedged values should be labeled
- **Whether hedging and revision occur in voice notes, occur in phrasing the cue lists cannot
  see, or are genuinely rare in bot-led WhatsApp sales chats.** Kapardhi's framing, 2026-10-03.
  These three replace the earlier (a)/(b)/(c) list and the separate question of whether the cue
  lists can fire at all, which the measurements below have narrowed into them.
  (1) **Voice notes.** 54 of the rejected turns were voice-note placeholders. A sampling-frame
  limit rather than a cue limit: no cue list recovers it, transcription could. Raised by Claude
  Code, 2026-10-03.
  (2) **Phrasing the cue lists cannot see.** Distinct from the ruled-out (b) below, and the
  distinction matters: (b) was that the lists were in the wrong *language*, which adding
  romanized forms tested and refuted. This is that the phenomenon is expressed in ways no word
  list catches at all -- syntactically ("I will have to check with my wife", "let me see"), or
  in spellings the exact-match forms miss, since "konchem" does not match "koncham". Recall on
  hedges is unmeasured anywhere in this experiment, so a word list's miss rate here is unknown
  rather than small.
  (3) **Genuinely rare in bot-led WhatsApp sales chats**, where customers state figures flatly
  and negotiate by phone, and where the seller side is a bot with human takeover the schema
  cannot distinguish. 22 field mentions with 0 hedge or correction matches across 286 turns is
  consistent with this.
  What the measurements have settled, so these three are what is left. Script: `ascii_only` 121
  of 135 eligible targets, `telugu` 1, and Kapardhi's reading that script blindness is ruled
  out. Pipeline: his reading that a fault is ruled out, text arriving and matching on both
  populations. The eligibility frame: the 3-word floor excludes 151 turns of which 4 are
  substantive, and on Kapardhi's decision of 2026-10-03 the floor stands, so the frame is no
  longer an open explanation. Per-cue hit counts, raised as a measurement that might separate
  these, are not one: they are entailed to be 0 while the census reads hedge 0 and correction 0,
  because the stratum is one alternation over the same forms.
  (b) ~~**English-only cues** missed code-mixed hedges and corrections.~~ **Ruled out on
  Kapardhi's reading, 2026-10-03.** The romanized Telugu and Hindi forms were added and the
  census re-run on the same corpus returned correction 0 and hedge 0, unchanged. Kept rather
  than deleted because a hypothesis that was tested and failed is a result, and because it is
  why the cue lists hold those forms now.
  None of (1), (2) and (3) is separable from this corpus's text: (1) predicts transcription
  recovers the hedges, (2) predicts a different instrument on the same text would, (3) predicts
  neither would. Nothing measured so far distinguishes them.
- Whether agreement measured on model-authored conversations transfers to real ones at all
  (EXP-000's synthetic subset is reported separately for exactly this reason)
- Gap between gold and predicted prior state (exposure bias)

## Risks
- **The abstention part of the research question may not be testable on this deployment's text.
  Flagged for the Stage 1 decisions, D2 and D4.** Kapardhi, 2026-10-03. Across all 286 customer
  text turns, 0 match any hedge or correction cue, and script blindness, cue language, pipeline
  faults and the eligibility frame are each ruled out or settled.
  Stated carefully, because a cue match is not a label and this file must not trade one for the
  other. The 0 is a fact about **enrichment**, not about what the annotators will write: the
  real subset is the 18 field-mention turns taken whole, and no cue selected any of them for
  carrying a hedge or a revision. Whether an individual turn earns `ABSTAIN:insufficient`,
  `ABSTAIN:ambiguous` or `ABSTAIN:conflicting` is the annotators' judgment and is not predicted
  by a cue list. What the 0 does mean is that nothing enriched the sample for those three
  categories, so against the pre-registered floor of 10 items per category counted as n_either,
  each is more likely to read "not interpretable" than to yield a kappa. That is the shape of
  the risk, not a derivation of the result.
  It bears on **D2** (contribution ordering: a benchmark-first claim needs a corpus that can
  carry the benchmark) and on **D4** (accepting ADR-003, since typed abstention is what this
  corpus may not be able to exercise). Recorded here and not in `STATE.md`'s Decisions pending,
  which is Kapardhi's to edit.
- Solo annotation: inter-annotator agreement impossible alone
- Synthetic-data circularity: same frontier model as generator, baseline, and judge
- No real conversations for the test set
- Pretrained SLMs have seen SGD/MultiWOZ: contaminates "unseen"
- Frontier solves the task cheaply: small-model motivation becomes cost/privacy (engineering)

## Unknown unknowns (assumptions we may not see)
- **Subjective fields** ("lead temperature"): gold is opinion, not extraction. In scope?
- **Speaker grounding:** an agent quoting a price is not the buyer's budget
- **Relative time** ("next month") needs timestamps in X
- **Terrible real schemas:** cryptic, undocumented CRM field names
- **Implicit state:** inferred, not stated values. In scope?

## Research clusters
| Cluster | Open questions |
|---|---|
| Data | Real conversation source? How much synthetic before circularity dominates? Can a state-sparse real corpus support an abstention benchmark, or does it need transcribed voice notes? |
| Representation | ABSTAIN in op stream or separate channel? Is CONFIRM needed? |
| Generalization | Does performance track the novelty ladder or raw lexical overlap? |
| Memory | Gold vs predicted prior state gap |
| Uncertainty | Verbalized vs logprob confidence; does calibration survive schema shift? |
| Efficiency | Where on 1B / 4B / 8B does the joint task collapse? |
| Evaluation | Exact-match metrics for ops and lineage without LLM judges |
