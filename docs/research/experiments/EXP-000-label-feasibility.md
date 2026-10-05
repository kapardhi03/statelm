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
- 2026-10-03: **v3 census — the extended cue lists change nothing.** Transcribed from
  Kapardhi, 2026-10-03, counts only: "135 eligible customer turns; field_mention 18;
  correction 0; hedge 0, unchanged from v2." His reading, recorded as his: the extended cues
  found no hedges or corrections, so **cue-language blindness does not explain the absence.**
  Two explanations remain: the phenomena are genuinely absent from the text channel, or they
  occur in the 54 voice notes. Pre-labelling; the run wrote sheets but none were labelled.
  What the counts measure is a **cue match**, not a hedge. Same corpus as v2, so v3 is not an
  independent sample; it carries the one bit that those 16 romanized forms add nothing.
  Internal consistency: every form in `cues.CODE_MIXED_CUES` is also a hedge or a correction
  cue, so `code_mixed_cue_hits` is necessarily 0 whenever those two strata are — and
  `report_census` suppresses the line at 0, so it was absent from the census rather than
  printed as 0. That also means the count carries no information independent of the two strata
  at the zero point: it can apportion a non-zero stratum, which is what it was added for, and
  cannot rule (b) in or out.
  The census path is the sampling path — `candidate_turns` -> `cues.strata_for` -> the
  module-level cue tuples — and `--census-only` returns only after `report_census`. Pinned by
  `tests/test_sample_items.py::TestCensusOnlyUsesTheExtendedCueLists`, whose corpus carries
  hedges and corrections in romanized forms only and whose control fixture is the same turns
  with those words removed, and by `TestCensusOnlyMatchesASamplingRun`, which compares the two
  invocations' censuses on one corpus. Neither ties the v3 run itself to this code version:
  no `runs/EXP-000/<run-id>/` record exists for the v2 or v3 census, so the counts above rest
  on Kapardhi's report rather than on an auditable run record. Flagged by Claude Code.
  **A caveat on the ruling-out, raised by Claude Code and not settled.** The 33 English hedge
  and correction forms in the same lists — "around", "maybe", "up to", "flexible", "actually",
  "sorry", "change" among them — also matched 0 of those 135 turns. No cue in either language
  has been observed to fire on this corpus, so the probe has not been shown capable of firing,
  and a probe that has never fired cannot separate an absent phenomenon from a probe that does
  not match this text. Recorded in `knowns-unknowns.md` as an open question with the two
  aggregate measurements that would settle it.
- 2026-10-03: **the v3 sampling run printed the synthetic set's stratum counts to Annotator A's
  terminal before labelling.** Reported by Kapardhi, 2026-10-03: "hedge 13, correction 5,
  code-mixed 13 among eligible synthetic targets. No item-level or row-level information was
  shown, and Annotator B saw nothing." The change that follows was instructed by Kapardhi in
  the same message, prompted by what the run printed; no label existed when it was made.
  The sampler now prints a `--synthetic` set's totals only; the breakdown goes to the manifest
  and `--show-synthetic-strata` prints it. Manifests from here on record
  `synthetic_strata_printed`, so a **future** run can be checked rather than guessed at; the
  v3 manifest predates the field, so that run is not auditable this way.
  Covered by `tests/test_sample_items.py::TestSyntheticStrataAreWithheld`, which also pins that
  the real census keeps its full breakdown — that census is the finding above.
  **Suppression does not undo the exposure already incurred.** Annotator A has seen those
  counts; re-running the sampler cannot unsee them, and a fresh draw from the same synthetic
  set carries the same base rates. What the change protects is runs after this one. Whether
  the v3 sheets should be marked unused, as the v2 sheets were, is not recorded here: they sit
  under `data/scrubbed/`, which Claude cannot read, and nothing in this record marks them
  either way.
  What the fix does not reach, recorded so the measurement is not read as cleaner than it is.
  The quotas are pre-registered and public, so the composition the sampler aimed for stays
  derivable from the turn count. And with real hedge 0 and correction 0, an item in the mixed
  set that reads as a hedge or a correction **is more likely synthetic than real** — an
  inference from the real census alone, which Annotator A must see, not from the counts that
  were printed. How much more likely depends on how completely the cues catch hedges in the
  real corpus, and that recall is unmeasured: the caveat in the entry above is that no cue has
  been observed to fire on this corpus at all, so a real hedge the cues missed would sit in the
  real subset and read as a hedge. The claim cannot be put more strongly than that without
  holding both "the cues may be blind to hedges here" and "a hedge-reading item must be
  synthetic", which are in tension. Stated conditionally for that reason, after review.
  To the extent it holds, it partially de-blinds the mixed set for Annotator A on exactly the
  strata the abstention hypothesis is about, and suppressing the synthetic counts removes the
  magnitude rather than the inference. Annotator B has seen none of it. Flagged by Claude
  Code; whether the design should change in response is Kapardhi's call, not recorded here as
  settled.
  A larger threat than the printed counts, flagged by Claude Code and settled by Kapardhi on
  2026-10-03: Annotator A approved the annotation guideline, so the real subset's kappa is
  partly guideline-approver against guideline-user. Both that and the derivability of which
  person is which letter are now carried as accepted limitations under **Known limitations**
  below, with the mitigation Kapardhi named.
- 2026-10-03: **`--cue-diagnostics`, and run records for census figures.** Instructed by
  Kapardhi, pre-labelling, prompted by the caveat in the v3 entry above: a 0 that every cue
  produces cannot separate an absent phenomenon from a probe that does not match the text.
  **What the per-cue counts can and cannot do, corrected after review.** While the census reads
  hedge 0 and correction 0, every per-cue count is **entailed** to be 0 and carries no
  information independent of the census: `cues.strata_for` sets the hedge stratum iff
  `has_hedge_cue` matches, that is one alternation over the same forms `per_cue_hits` matches
  one at a time, over the same eligible targets, and an alternation matches iff some alternative
  does. This is the same mistake this record identified two entries ago for
  `code_mixed_cue_hits` and it was reintroduced here; the correction is Claude Code's, after
  review. The per-cue half earns its place on a corpus whose strata are not zero, where it
  apportions them, and as a record of exactly which forms were probed. **On this corpus the
  discriminating measurements are the other three:** the script mix, the field-keyword and
  field-pattern counts, and the script of the probe strings themselves.
  The flag reports, counts only, over the eligible targets of `--input`: per-cue hit counts for every form in both lists and per-keyword counts
  for every field keyword, zeros included; and the script mix of those turns, by Telugu block
  (U+0C00-U+0C7F), Devanagari (U+0900-U+097F), other non-ASCII and ASCII-only. The same two
  summaries cover the field keyword lists, and the cue and keyword strings' own script is
  reported too, because an ASCII probe cannot match a native-script spelling however well its
  words are chosen. A synthetic set is excluded by construction, so diagnosing the real corpus
  cannot prime the labelling of the synthetic one.
  `--census-only` and `--cue-diagnostics` now each write `runs/EXP-000/<run-id>/config.json`
  with the git commit, a corpus hash and a digest of the exact cue and keyword lists measured
  with, alongside `census.json` and `cue_diagnostics.json`. This is what the v2 and v3 censuses
  lacked: their figures rested on a report and could not be re-derived.
  **No longer, as of commit `b031a8d`.** Kapardhi pushed `runs/EXP-000/20261003T163331Z-b860436/`
  and `runs/EXP-000/20261003T164527Z-2773803/`, so every census and cue-diagnostic figure in this
  record is now re-derivable from a tracked file rather than from a relayed count. Both runs read
  one corpus (47 files, `sha256 e50b0d40...`) against one probe
  (`sha256 3c1b9ce4...`, 18 correction and 31 hedge forms of which 16 code-mixed), so they are
  directly comparable. Two provenance caveats: `20261003T164527Z-2773803` carries
  `git_tree_dirty: true`, so its commit alone does not pin the code, though its probe digest is
  identical to the clean run's and therefore the word lists were the same; and both runs read
  `data/scrubbed/EXP-000-v2`, not the `data/scrubbed/EXP-000` the run book names.
  **`census.json` and `cue_diagnostics.json` are tracked by git. Kapardhi's decision,
  2026-10-03: "Keep them tracked."** They join `config.json` and `metrics.json`, which already
  were, so that a census figure is re-derivable from the repository rather than resting on a
  report. Claude Code made the change first and then flagged it as one that should have been
  asked rather than decided, since what gets tracked from client-derived data is set by
  `.claude/rules/data-privacy.md`, which is Kapardhi's; he confirmed it. The rule's own line
  that "only aggregates -- counts, Cohen's kappa, confusion matrices -- go into `runs/`" already
  permitted the content; what Claude Code should not have assumed is which of those files git
  carries.
  "Counts only" is the intent, not the literal content: every **string value** in these records
  is a cue, a field keyword, a field name, a script label or one of two fixed notes, and
  `config.json` additionally carries a commit, a platform string, paths and hashes. Three tests
  hold the property -- an allowlist over every string, no `conv_` id or `SPEAKER_` id, and a
  record taken over a native-script corpus decoding as pure ASCII -- with two gaps worth naming:
  the allowlist skips keys it treats as run metadata, and accepts any lower-case identifier as a
  dict key. Neither is reachable from corpus text given the code, which is why the construction
  matters more than the tests here. A
  `--synthetic` set's census is kept out of the tracked record, since its per-stratum counts
  are the ones Annotator A must not meet before labelling. A field whose keyword list came from
  `--field-keywords` has its counts recorded in that file's own order and its keywords named
  nowhere, so that the option can be pointed at a list that stays on one machine. **It buys
  nothing for the list the run book actually uses**, and the entry first claimed otherwise:
  `experiments/EXP-000/field_keywords.yaml` is a tracked file naming all 24 localities, so for
  that file the redaction protects what is already published, and the counts are readable off
  it in order anyway. Corrected after review. The built-in lists are named, being repository
  content already.
  **What the diagnostic cannot do, stated after review rather than before it.** It says whether
  the probe *did* fire on this corpus, not whether it can: a cue match is not a hedge, so
  firing licenses "the matcher is lexically live on this text" and never "the phenomenon is
  there". Cue recall on hedges is unmeasured anywhere in this experiment.
  Nor is "nothing fired" binary between an absent phenomenon and a blind instrument. A third
  cause is the sampling frame: `MIN_TARGET_WORDS` is 3 and seller turns and media placeholders
  are ineligible, which removes exactly the turns where a hedge is shortest -- "maybe",
  "around 40", "pata nahi" are one or two words. The v2 census counted 54 voice-note
  placeholders beside its `too_short` rejections. A corpus-wide zero can come from the frame,
  which is neither of the two readings.
  And the v2/v3 counts already bound the strongest version of the instrument claim: with
  `field_mention` 18 of 135, ASCII matching demonstrably fires on at least 18 of those turns,
  so "the instrument cannot reach this text" could at most hold for the other 117.
  What the script mix adds is specific: turns holding words in the Telugu or Devanagari blocks
  are out of reach of every ASCII form, however many romanized words are added. Whether any of
  this reopens explanation (b) is Kapardhi's call.
- 2026-10-03: **script blindness ruled out; the word floor is now the open frame question.**
  Transcribed from Kapardhi, 2026-10-03, counts only: the script-mix diagnostic ruled out script
  blindness, `ascii_only` 121 of 135 eligible targets, `telugu` 1. His reading, recorded as his.
  **Corrected against the run file, 2026-10-05.** This entry first said his two figures account
  for 122 of the 135 and "the remaining 13" sit in the other buckets. That arithmetic was wrong:
  only `ascii_only` is exclusive, while `telugu`, `devanagari` and `other_non_ascii` are
  "contains", so they overlap and do not sum to the complement. From
  `runs/EXP-000/20261003T164527Z-2773803/cue_diagnostics.json`, `script.eligible_targets`:
  `ascii_only` 121, so **14** of the 135 hold some non-ASCII character, not 13. Those 14 split
  into `with_non_ascii_letters` **7** and `other_non_ascii_detail.symbols_only` **7** — the
  second group being a currency sign or similar, which leaves every word matchable. The bucket
  counts themselves are `telugu` 1, `devanagari` 6, `other_non_ascii` 9, which is 16 memberships
  over those 14 turns.
  What this settles and what it leaves. 121 eligible targets are pure ASCII and every cue form
  scored zero on them, so the probe was not blocked by the writing system on the great majority
  of the corpus. By the entry above, that is **not** evidence the phenomenon is absent: it
  leaves cue coverage (16 romanized forms are exact strings, and recall on hedges is unmeasured)
  and it leaves the eligibility frame.
  **The frame is now the measurable one, so `--cue-diagnostics` was extended to measure it.**
  Instructed by Kapardhi, pre-labelling. A separate block reports, over the customer text turns
  the 3-word floor excludes and counts only: field mentions per field, `amount_pattern` and
  locality matches, hedge and correction hits per form including zeros, and the word-count
  distribution. The question it answers is whether the floor discards short but substantive
  answers -- "50 lakhs", "3 BHK", "maybe 60" are one or two words each and each settles or
  hedges a field. The floor itself is pre-registered and unchanged; this measures what it costs.
  Reported per field and per pattern rather than per keyword, so a `--field-keywords` list kept
  off the machine is not named in a tracked record. **No threshold.** The block prints its
  counts and no verdict: whether the cost is too high for the floor to stand is Kapardhi's call,
  and a threshold set after seeing the number would not be pre-registered. Selection is by
  `cues.target_rejection` returning `too_short`, the same predicate that decides eligibility, so
  the two populations are exact complements and a seller turn, a media placeholder and an empty
  turn each stay out under their own reason.
- 2026-10-03: **what the word floor excludes, measured; the floor stands.** Run
  `20261003T164527Z-2773803`. Transcribed from Kapardhi, 2026-10-03, counts only: 151 excluded
  short turns, 126 one-word and 25 two-word; 4 with a field mention; 0 hedge or correction cue
  hits.
  **Decision, transcribed from Kapardhi, 2026-10-03:** "the 3-word floor stands; it excludes at
  most 4 substantive turns. The v3 sheets are used as built."
  "At most 4" is the right register and is exactly 4 on the block's own definition: with 0 cue
  hits, no excluded turn carries a cue, so the turns holding a field mention *or* a cue are the
  4. The floor is pre-registered and unchanged, and this is the first run whose figures are
  tied to a commit and a corpus hash rather than relayed -- the run id's `2773803` is the commit
  that built the block it reports. Verified against the pushed file on 2026-10-05: its
  `excluded_by_word_floor` block reads turns 151, `word_counts` {"1": 126, "2": 25},
  `with_field_mention` 4, `with_hedge_or_correction_cue` 0, every figure as transcribed.
  The corpus-wide arithmetic closes: 135 eligible + 151 too_short = **286 customer text turns**,
  of which 18 + 4 = **22 mention a tracked field** and **0 match any hedge or correction cue**.
  Recorded in `knowns-unknowns.md` under Known, with Kapardhi's reading that script blindness
  and pipeline faults are ruled out.
  **Two consequences of using the v3 sheets as built, neither of them a re-opening of the
  decision.** First, it closes an item this record had left unmarked either way: the v3 sheets
  are neither void nor unused, and nothing further is owed on them. Second, those sheets came
  from the run that printed the synthetic set's stratum counts to Annotator A's terminal, so the
  labels they produce carry that exposure. The entry of 2026-10-03 above records it and records
  that suppression protects later runs rather than this one; using the sheets as built is what
  makes that entry bear on a kappa rather than on a hypothetical.
- 2026-10-05: **media placeholders measured by kind.** Run
  `20261005T191447Z-072dbbc`, clean tree, same corpus as the two 2026-10-03 runs (47 files,
  `sha256 e50b0d40...`) and the same probe (`sha256 3c1b9ce4...`). Transcribed from
  `census.media_placeholder_kinds`, counts only: **voice 29**, image 20, contact 2,
  unsupported 2, video 1, document 0, other 0. The seven kinds sum to the 54 that
  `rejected.media_placeholder` records, so none is unaccounted for, and the voice share is
  29 of 54, or 53.7%.
  Nothing else in the census moved: 623 turns read, 135 eligible, `field_mention` 18 with the
  same per-field split, `correction` 0, `hedge` 0, `code_mixed_cue_hits` 0. This run adds the
  breakdown and nothing else.
  **One figure this reconciles against.** The entry of 2026-10-03 transcribes Kapardhi's count
  as "54 voice-note placeholders", and the v2 Known bullet in `knowns-unknowns.md` carried the
  same wording. That was recorded before any breakdown existed; the measured number of voice
  notes is 29, not 54. His transcription is left as he gave it, with the measured figure beside
  it in both files.
  **What the 29 means is not recorded here.** Explanation (1) under Unknown needs the rejected
  media turns to be speech, and 29 is now the measured number rather than a characterisation.
  Whether that is enough for the explanation is Kapardhi's reading; this entry transcribes the
  count and stops.
- 2026-10-06: **Kapardhi's reading of the media split.** Transcribed from Kapardhi,
  2026-10-06, verbatim: "Explanation (1) is not ruled out. 29 voice notes sit beside 135
  substantive customer text turns (about 18%), and voice is where loose, hedged speech is most
  likely. It is the only one of the three explanations testable directly, by listening to the 29
  notes locally. Whatever that shows, 47 conversations cannot carry an abstention benchmark on
  their own: even 29 of 29 would be too few. The real corpus is at most a validation slice. This
  bears on D2, which stays open until EXP-000 has labels."
  Recorded under explanation (1) in `knowns-unknowns.md`, and the Risks entry there is narrowed
  to match: the risk is no longer only that the abstention question may be untestable on this
  text, but that on his reading the corpus cannot carry the benchmark whatever the 29 notes hold.
  His three figures check against run `20261005T191447Z-072dbbc`: 29 is
  `media_placeholder_kinds.voice`, 135 is `eligible_targets`, and 47 is `inputs.corpus.files`,
  one conversation per file. "About 18%" is 29 of 164, voice as a share of substantive text plus
  voice; 29 of 135 alone is 21.5%. Noted so the denominator is on the record rather than
  re-derived later, not as a correction.
  Claude Code adds nothing to the reading. One consequence for this experiment's own scope,
  which is engineering rather than interpretation: "at most a validation slice" is about what the
  corpus can support downstream and changes nothing about EXP-000's measurement, whose Result,
  Interpretation and Decision stay empty until the sheets are labelled.

## Known limitations
Accepted rather than fixed, and no action is asked for. The two bullets below are what Kapardhi
instructed on 2026-10-03, in his terms. Anything Claude Code adds to them is marked as such and
is a flag, not part of his instruction.

- **Annotator A approved the annotation guideline**, so the real subset's kappa is partly
  guideline-approver against guideline-user rather than two independent users of it.
  **Mitigation, named by Kapardhi: Annotator B's reading is independent.**
  *Flagged by Claude Code, not part of the above.* (i) Kappa is a pairwise statistic, so one
  naive rater makes one side of the pair a genuine guideline user; it does not make the pair the
  "two independent human annotators" the Hypothesis names. The mitigation is partial by
  construction. (ii) Guideline approval is the narrower half of the asymmetry and the entry of
  2026-10-02 reads the approval the other way, as settling how labels are applied rather than
  whether the taxonomy is right. The wider half is that A also owns ADR-003, the pilot field
  list, the cue lists, the HEDGED rule and every pre-registered measurement choice. (iii) The
  only sourced statement about what B has seen is Kapardhi's report of 2026-10-03, that B saw
  nothing of the synthetic stratum counts. The **real** census is published in this repository
  and in `knowns-unknowns.md`, so B's naivety does not extend to it.
- **Which person is Annotator A is derivable within this repository.** Accepted by Kapardhi,
  2026-10-03. It is derivable from this record alone in two sentences: the 2026-10-02 entry
  names Kapardhi as the guideline's approver and the entry above names Annotator A as its
  approver. The run book also addresses A directly as the person who runs the local tools.
  *Flagged by Claude Code, for Kapardhi to amend or leave:* the Setup sentence that which person
  is which letter "is not recorded in this repository" is stronger than what holds, and Setup is
  his. The part that protects the measurement does hold: no personal name appears in a sheet,
  the manifest, the disagreement list or the metrics. The same overclaim stood in
  `experiments/EXP-000/README.md`, which is Claude Code's to fix, and has been corrected there.

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
