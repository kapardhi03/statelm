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

## Unknown (to test)
- Whether H-A / H-B / H-C hold
- Frontier headroom on this exact task (EXP-001)
- Human agreement on abstention types (EXP-000)
- Size threshold for the joint task
- How hedged values should be labeled
- Why real customer turns are state-sparse. Three explanations, none ruled out:
  (a) **voice notes** carry the hedging and self-correction, so the text channel systematically
  lacks them. 54 of the rejected turns were voice-note placeholders. This is a sampling-frame
  limit rather than a cue limit: better cue lists cannot recover it, transcription could.
  Raised by Claude Code, 2026-10-03.
  (b) **English-only cues** missed code-mixed hedges and corrections. Partly testable now: the
  romanized Telugu and Hindi forms were added on 2026-10-03 and the census reports how many
  eligible turns they match, so a re-run separates this from (c).
  (c) the **phenomenon is genuinely rare** in WhatsApp sales chat, where customers state figures
  flatly and negotiate by phone. 10 budget mentions with 0 hedge matches is consistent with this.
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
