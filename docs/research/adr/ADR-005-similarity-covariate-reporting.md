# ADR-005: Embedding similarity is reported as a calibrated, coarse covariate

Status: Proposed
Date: 2026-10-01
Revised: 2026-10-02
Supersedes: none

## Decision
Embedding similarity is reported as a **within-model rank or stratum**, computed with **at least
two encoders**, and **never compared against an absolute cutoff**.

- **Granularity: at most two strata, or a continuous covariate. No finer strata**, and no
  conclusion is drawn from adjacent strata.
- **Calibration: each encoder is calibrated on known same-meaning pairs before its similarity is
  interpreted**, and the calibration is reported alongside the figure it qualifies.

Calibration interprets an encoder's scale; it does not license a cutoff. Knowing that same-meaning
pairs sit at a given level under one encoder says what a number means there, and it still does not
make "above 0.8" a finding.

This governs how the covariate ADR-004 mandates is reported. It does not change ADR-004: novelty
levels come from construction, and similarity assigns nothing.

## Why
EXP-002 measured similarity two ways and the results diverge on scale while agreeing on order.

- **An absolute cutoff is not comparable across encoders.** At cosine 0.8, H1's rate was 12.20%
  under all-MiniLM-L6-v2 and 41.46% under bge-base-en-v1.5.
- **A cutoff can sit below the scale of identity-preserving rewording, invisibly.** Of known
  same-slot paraphrases, 67/160 fall below 0.8 under MiniLM at v1 and 111/160 at v5; under BGE,
  9/160 and 42/160. Under MiniLM the bar was stricter than a genuine paraphrase, and nothing in
  the figure itself showed that. This is what the calibration requirement exists to surface.
- **Ranks survive a change of encoder where cutoffs do not.** In H2 both encoders produced the
  same Spearman rho to the digit, with the inversion in the same place, while their absolute
  means sat 0.08 to 0.10 apart.
- **Fine granularity is not supported, and is fragile to more than encoder choice.** v4 and v5
  inverted under both encoders, by 0.000483 and 0.003926, against a per-slot p10-p90 spread of
  roughly 0.11. The post-hoc 44-pair diagnostic (below) moved the same five-point statistic from
  rho = -0.9 to -0.7 on a different population of the same data, reversing the verdict. A
  statistic that moves that far on a population change should not carry per-stratum conclusions.

## Assumptions
- Known same-meaning pairs exist for each dataset the covariate is used on. True for SGD-X, whose
  variants are paraphrases of the same slot. **Not established anywhere else**, and this ADR gives
  no procedure for obtaining them, so it can block use of the covariate on a dataset that has none.
- Two strata are enough for the claims the benchmark makes. Untested.
- Rank stability observed on paraphrase distance carries over to other similarity relations,
  including similarity to the nearest train field, which EXP-002 did not measure.
- Two encoders suffice to catch an encoder-specific artifact. Weakly tested: EXP-002's two are
  both English web-trained sentence encoders and their Cohen's kappa on the deciding call was
  0.328.

## Alternatives
- **Finer strata with intervals.** More informative if the strata are separable. EXP-002 is
  evidence they are not, at five levels, under either encoder.
- **Per-encoder calibrated cutoffs.** Partly adopted and partly rejected: calibration is now
  required, thresholding on it is still forbidden. Allowing the cutoff back would need an
  experiment showing a calibrated bar is stable across encoders.
- **One encoder, absolute cutoff.** What H1 did. Its verdict depends on which encoder is chosen.
- **Raw cosines, no rank, no calibration.** Honest and not comparable across items or runs.
- **Human similarity judgments.** Closest to the construct, most expensive, and needs its own
  agreement study first.

## Failure modes
- **Two strata may be too coarse to show a real effect**, so a null result under this rule can be
  a reporting artifact rather than a finding. That is a cost of the rule, not an argument against
  reporting it.
- **"At most two strata" invites a median split**, which is a cutoff wearing different clothes.
  This ADR does not settle where a stratum boundary may come from, and that gap should close
  before strata appear in a claim.
- **Calibration inherits its pairs' construction.** Same-meaning pairs define sameness by how
  they were built, so the calibration carries that definition's biases into every figure it
  qualifies.
- **Ranks hide magnitude** by design: two items adjacent in rank can be far apart in similarity.
- **Agreement for the wrong reason.** Encoders of one family can agree through a shared bias.
  "At least two" is a floor, and different families should be preferred.
- **Encoder contamination.** SGD has been public since 2019 and SGD-X since 2021, so both
  encoders may have seen these schemas. Rank stability could be an artifact of that.

## Consequences
- Easier: a reported covariate survives a change of encoder; no number rests on an uncalibrated
  bar; a figure arrives with the evidence for what its scale means.
- Harder: every similarity figure needs at least two encoder runs plus a calibration set.
- **Two hypothesis forms already used in EXP-002 are not reusable under this ADR.** H1's shape, a
  proportion clearing a cosine threshold, is forbidden by the no-cutoff rule. H2's shape, a
  five-point ordering test across strata, is forbidden by the two-strata rule. Future hypotheses
  about similarity have to be written as a continuous covariate, a two-stratum contrast, or a
  paired comparison.

## Evidence
- **EXP-002 H1**, run `20261001T180031Z-746c803`: 12.20% against 41.46% at the same cutoff, and
  the calibration reference showing the cutoff below same-slot paraphrase scale under one encoder.
- **EXP-002 H2**, same run: identical Spearman rho across encoders with the inversion in the same
  place, absolute means 0.08 to 0.10 apart, v4/v5 inverted under both.
- **Post-hoc, labelled post-hoc and not pre-registered:** the 44-pair seen-service diagnostic in
  EXP-002's Result. On that population the same statistic gives rho = -0.7 under both encoders
  and the H2 verdict reverses, while condition (a) still holds. It is cited here for the
  granularity rule only, and it decides nothing on its own.
- **Scope of the evidence:** all of it concerns **paraphrase distance**, the cosine of a slot to
  its own paraphrase. **Similarity to the nearest train field, the relation ADR-004 stratifies
  by, is untested.** This ADR generalizes to it without evidence, which is the weakest link in it.
