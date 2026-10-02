# VOID — EXP-000 run 20261002T175103Z-f318529

**Declared void by Kapardhi, 2026-10-02. This run's numbers must not be used, cited, or
aggregated with any other run. The directory is kept deliberately: a void run is evidence about
the instrument, and deleting it would destroy the only record of why the sampler changed.**

## What happened

Transcribed from Kapardhi, 2026-10-02:

> Void: all 160 labels NO-OP, kappa undefined. Cause is the sampling design, not the annotators:
> 10 of 16 sampled turns were seller-side (structurally NO-OP under the Q3 rule), customer turns
> sampled were mostly 2-16 characters or a voice note, and the hedge/correction cues matched
> seller text. Sheets showed SPEAKER_n, not role.

## What that means for the experiment

There is no result here, not a negative one. With every label NO-OP in both sheets, expected
agreement is 1 and Cohen's kappa has no defined value; `kappa.cohen_kappa` returns None for
exactly this case rather than 1.0 or 0.0. The run says nothing about whether annotators can
distinguish the abstention types, which is what EXP-000 exists to measure, so it informs
ADR-003 not at all.

Two counts are consistent with the recorded setup and support the account above: 16 turns x 5
pilot fields = 80 items, and 80 items x 2 annotators = 160 labels.

## Why the sampler, not the annotators

The sampler drew its targets from **every** turn. Under the annotation guideline's rule §3.3,
decided 2026-10-02, a seller turn never establishes a customer field — so a seller target is
NO-OP by construction, whatever an annotator thinks. That made 10 of the 16 targets unable to
carry information. The short customer turns ("ok", "yes") and the voice-note placeholder could
not carry a field value either.

This was knowable when rule §3.3 was decided, which was before this run. The rule and the
sampler's target selection were changed in the same day's work and the interaction between them
was not checked. That is a miss in the engineering, recorded here rather than left implicit.

## What changed because of it

Pre-registered in `experiments/EXP-000/thresholds.py` and logged in the experiment record's
Change log, all of it decided by Kapardhi on 2026-10-02 **after** this run produced no kappa and
therefore in the light of no result:

1. Targets are customer turns of real text only; seller turns and media placeholders stay in the
   context, where rule §3.3 needs them, but are never the turn being labelled.
2. A target needs at least 3 words.
3. Cues are matched against the target turn's own text only. This was already true of the code;
   what made the cues select seller text was that seller turns were eligible targets.
4. A `field_mention` stratum, with quotas field_mention 40% / correction 20% / hedge 20% /
   random 20%, shortfalls reported.
5. Sheets show `turn_role` (customer / seller), not `SPEAKER_n`, in both the target and the
   context.
6. The sampler prints the eligible-target census — total and per stratum — **before** writing
   sheets, so an under-supplied corpus is visible while it can still be acted on.

## Files

The sheets, the manifest and the disagreement list for this run stay on Kapardhi's machine under
the gitignored trees. `metrics.json` and `config.json` from this run are aggregates only and are
committable if he wants the void run's numbers preserved in the repository alongside this marker.
