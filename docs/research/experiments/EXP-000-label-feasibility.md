# EXP-000: Label feasibility (abstention agreement)

Status: Planned
Owner: Kapardhi
Created: 2026-10-01
Decision informed: ADR-003 (keep, merge, or redefine abstention types)
Blocked by: nothing

## Hypothesis
Two independent human annotators agree on NO-OP vs value vs ABSTAIN type at κ ≥ 0.6 per
abstention type. Refuted if any abstention type falls below 0.6.

## Setup
- 60–100 (field, turn) items from realistic sales conversations, enriched for corrections,
  hedges, and multi-speaker turns.
- **Inter-annotator design**, two annotators, referred to only as **Annotator A** and
  **Annotator B**. No personal name appears in any annotation artifact: not the sheets,
  the manifest, the disagreement list or the metrics. Which person is which letter is
  not recorded in this repository.
- Both sheets hold the same items, each in its own seeded order, recorded in the
  sampler's manifest. Neither annotator can anchor on the other's sequence, and items
  are paired by item id rather than by row.
- They label independently, without discussion until both sheets are complete, using a
  written guideline (`EXP-000-annotation-guideline.md`).
- Agreement is computed in inter mode: `agreement.py --sheets sheet_A.csv sheet_B.csv`.
- Labels: NO-OP / VALUE(v) / ABSTAIN:insufficient / ABSTAIN:ambiguous / ABSTAIN:conflicting /
  HEDGED (kept separate to learn how people treat hedges).

### What Claude Code may build
- Item sampler and annotation sheet generator (one row per field × turn, context shown)
  (sample_items.py), run locally by Kapardhi
- Agreement script: Cohen's κ per category, confusion matrix, list of disagreements
- Draft of the annotation guideline (human edits and approves it)
- PII scrubber (scrub.py), run locally by Kapardhi
- Conversation extractor (extract.py), run locally by Kapardhi

### What Claude Code must not do
- Pre-label items, suggest labels, or act as an annotator. Model judgment and human judgment
  must stay distinct.

## Baseline
Chance agreement (κ = 0).

## Metric
Cohen's κ per category. Working threshold κ ≥ 0.6 per abstention type.

## Pre-registered measurement choices
Decided by Kapardhi, 2026-10-02, before any sheet was labelled. Implemented in
`experiments/EXP-000/thresholds.py`, which names the provenance of each value. Nothing here may
change after a real run has been seen; if one must, the change and its reason are recorded below.

| | Choice | Why it was a choice at all |
|---|---|---|
| Interpretability floor | A category with fewer than 10 items (`n_either`, the count of items *either* rater put in it) is reported with all its counts and marked **not interpretable**, never dropped or hidden. The hypothesis reads *cannot be evaluated* rather than passing when an abstention type falls below it. | Three agreed items give κ = 1.000, which would otherwise look like the strongest result in the table. |
| Bootstrap unit | Primary: **conversation** (cluster bootstrap). Secondary: item, reported but never the headline. | Five fields times one turn means five items sharing one conversation's context, so items are not independent and an item-level interval is too narrow. |
| Undefined replicates | Excluded from the percentile interval and counted. Above 5% undefined the interval itself is marked not interpretable. | A replicate in which the category does not appear has no defined κ. Scoring it 0 would bias the interval downward; dropping it silently would describe only the resamples where the category happened to appear. |
| Value agreement | **strict** normalization (case, whitespace, trailing punctuation) is the primary figure. A **number-aware** figure, which resolves magnitude words so "40-45 lakhs", "40 to 45 lakhs" and "40–45 L" are equal, is reported separately and never replaces it. | Strict is a lower bound that cannot flatter the annotators. The gap between the two says how much value disagreement is formatting. Hedge words are deliberately *not* collapsed, since HEDGED is a label of its own. |
| HEDGED | **Rule (a):** HEDGED records the tentative value in the value column ("might stretch to 45" -> label HEDGED, value 45). | `research-question.md` lists hedged statements as Unresolved. This fixes an operational rule so annotation can proceed; it does not resolve the question, and the note there says so. |
| Threshold comparison | κ ≥ 0.6 with a 1e-9 tolerance. | A one-vs-rest table of (2, 1, 1, 14) has an exact κ of 3/5 but computes as 0.5999999999999996, so a bare comparison would report BELOW on a category that exactly meets the threshold. n = 18 is an ordinary size for a rare abstention type here. Added 2026-10-02, before any real run; a test pins the table and fails if the hazard ever disappears. |

ADR-003 was **Proposed** when these were pre-registered, and D4 is pending. EXP-000 is the
experiment that tests ADR-003, so every choice above is provisional on a taxonomy that may change.

### Change log
- 2026-10-02: measurement choices above pre-registered by Kapardhi. No sheets labelled yet.
- 2026-10-02: D3 resolved. Conversations are available from the ARTHRYX database; a second
  annotator is identified (Annotator B); the design is inter-annotator. The remaining blocker
  is approval of the annotation guideline.
- 2026-10-03: **v2 census, and a design change to a mixed item set.** Pre-registered: no sheet
  from the v2 sampling run was labelled, and the sheets it produced are marked unused in their
  manifest. Transcribed from Kapardhi, 2026-10-03, counts only: "135 eligible customer turns;
  field_mention 18 (budget 10, property_type 3, location 3, decision_maker 2, timeline 1);
  correction 0; hedge 0; 54 voice-note placeholders. The real corpus cannot support the
  abstention hypothesis." The design therefore changes to a **mixed item set**: every eligible
  field-mention turn from the real corpus (`--all-stratum field_mention`, no random top-up),
  plus 16 turns from a synthetic set sampled under the normal quotas.
  **Only the real subset's verdict bears on ADR-003.** The synthetic conversations were written
  by Claude Code (`claude-opus-5`), which knows the taxonomy and wrote the annotation guideline,
  so agreement on them measures whether two people can apply that guideline to text authored
  against it. `agreement.py`, `metrics.json` and this record label that subset
  "guideline usability, not evidence for ADR-003". Kapardhi's decision, 2026-10-03. The set and
  its limits are described in `experiments/EXP-000/synthetic/README.md`; it is an instance of a
  risk `knowns-unknowns.md` already records, synthetic-data circularity.
  No sheet reveals which subset an item came from: the source lives in the sampler's manifest,
  and sheet-facing conversation ids are per-run aliases drawn from one namespace, because a
  `syn_` prefix in an item id would tell an annotator the turn was model-written.
- 2026-10-03: hedge and correction cues extended with romanized Telugu and Hindi forms
  (Kapardhi's list: konchem, approx ga, emo, anukuntunna, chuddam, alochistanu, telidu, shayad,
  lagbhag, thoda, dekhte hain, pata nahi, around about; kaadu, ledu ledu, matlab, nahi nahi,
  change). Pre-labelling, prompted by the census above: 135 eligible turns produced 0 matches
  against the English-only lists in a deployment where customers code-mix. The census now also
  reports how many eligible turns matched a code-mixed form, so the next run can say whether the
  English-only lists were the problem or the phenomenon is absent from the text channel.
  `--census-only` prints the census and writes nothing, so a corpus can be inspected before a
  sample is committed to.
- 2026-10-02: **run 20261002T175103Z-f318529 declared VOID by Kapardhi.** Transcribed from
  Kapardhi, 2026-10-02: "Void: all 160 labels NO-OP, kappa undefined. Cause is the sampling
  design, not the annotators: 10 of 16 sampled turns were seller-side (structurally NO-OP under
  the Q3 rule), customer turns sampled were mostly 2-16 characters or a voice note, and the
  hedge/correction cues matched seller text. Sheets showed SPEAKER_n, not role." The run
  directory is kept and marked with `runs/EXP-000/20261002T175103Z-f318529/VOID.md`; its numbers
  must not be used, cited or aggregated. It produced no kappa, so it informs ADR-003 not at all.
- 2026-10-02: sampler changes pre-registered by Kapardhi, prompted by the void run. Because that
  run produced no kappa, none of these was chosen in the light of a result; what they were chosen
  in the light of is the sampling failure above. Implemented in
  `experiments/EXP-000/thresholds.py`, which names the provenance of each value.
  (1) Targets are customer turns of real text only; seller turns and media placeholders stay in
  the context, where guideline §3.3 needs them, but are never the turn labelled.
  (2) A target needs at least 3 words.
  (3) Cues are matched against the target turn's own text only; this was already true of the
  code, and what made the cues select seller text was that seller turns were eligible targets.
  (4) New `field_mention` stratum; quotas field_mention 40% / correction 20% / hedge 20% /
  random 20%, shortfalls reported. The `multi_speaker` stratum keeps no quota and is reported
  for interest only.
  (5) Sheets show `turn_role` (customer / seller) rather than `SPEAKER_n`, in the target and the
  context, because §3.3 turns on who spoke.
  (6) The sampler prints the eligible-target census, total and per stratum, before writing any
  sheet, so a corpus that cannot support the quotas is visible beforehand.
- 2026-10-02: annotation guideline approved by Kapardhi. EXP-000 is unblocked and ready to
  run. ADR-003 is still Proposed and D4 is still pending: the approval settles how the labels
  are applied, not whether the taxonomy is right, which is what this experiment measures.
- 2026-10-02: the three guideline boundary rules settled by Kapardhi and recorded in
  `EXP-000-annotation-guideline.md` §3. One of them bears on a measurement: approximations are
  VALUEs ("around 40 lakhs" -> VALUE `~40 lakhs`), so value agreement treats an approximation
  marker as part of the value. `~40 lakhs` and `around 40 lakhs` agree; neither agrees with
  `40 lakhs`. Pre-registered before any sheet is labelled.

## Leakage check
Items used here are pilot items and must not enter the eventual test split.

## Result
(pending)

## Interpretation
(pending)

## Decision
(pending, human)

## Note on solo annotation
If no second annotator exists, intra-annotator agreement (relabel after ≥1 week, blind to first
labels) is a weaker fallback and must be reported as intra-annotator, not inter-annotator.
