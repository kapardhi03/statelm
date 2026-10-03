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

## Unknown (to test)
- Whether H-A / H-B / H-C hold
- Frontier headroom on this exact task (EXP-001)
- Human agreement on abstention types (EXP-000)
- Size threshold for the joint task
- How hedged values should be labeled
- Whether the cue lists can detect these phenomena in this text at all. The 33 English hedge
  and correction forms in the lists — "around", "maybe", "up to", "at least", "flexible",
  "actually", "sorry", "change" among them — matched 0 of the same 135 eligible customer turns.
  No cue in either language has been observed to fire on this corpus, so the probe has not been
  shown capable of firing, and a probe that has never fired cannot separate "the phenomenon is
  absent" from "the probe does not match this text" — or from the text not being what the
  pipeline is assumed to deliver. This bears directly on the ruling-out of (b) below. Two
  aggregate measurements would settle it, both runnable locally and reporting counts only:
  per-cue hit counts, and the fraction of eligible turns holding any non-ASCII script or any
  non-English token. Raised by Claude Code, 2026-10-03; neither has been run.
- Why real customer turns are state-sparse. Three explanations; (b) ruled out on Kapardhi's
  reading of the v3 census, 2026-10-03, two remaining:
  (a) **voice notes** carry the hedging and self-correction, so the text channel systematically
  lacks them. 54 of the rejected turns were voice-note placeholders. This is a sampling-frame
  limit rather than a cue limit: better cue lists cannot recover it, transcription could.
  Raised by Claude Code, 2026-10-03.
  (b) ~~**English-only cues** missed code-mixed hedges and corrections.~~ **Ruled out on
  Kapardhi's reading, 2026-10-03.** The romanized Telugu and Hindi forms were added and the
  census re-run on the same corpus returned correction 0 and hedge 0, unchanged. Kept here
  rather than deleted because a hypothesis that was tested and failed is a result, and because
  it is the reason the cue lists now hold those forms. The caveat above is not settled against
  it: the ruling-out rests on 16 exact-match romanized strings, and nothing has yet shown that
  any cue, in any language, matches this corpus.
  (c) the **phenomenon is genuinely rare** in WhatsApp sales chat, where customers state figures
  flatly and negotiate by phone. 10 budget mentions with 0 hedge matches is consistent with this.
  On Kapardhi's reading, (a) and (c) are the live pair, and they are not separable from text
  alone: (a) predicts the hedges are recoverable by transcription, (c) predicts they are not.
  Nothing in the current corpus distinguishes them.
- Whether agreement measured on model-authored conversations transfers to real ones at all
  (EXP-000's synthetic subset is reported separately for exactly this reason)
- Gap between gold and predicted prior state (exposure bias)

## Risks
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
