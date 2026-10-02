# ADR-005: Embedding similarity is reported as a calibrated, continuous covariate

Status: Accepted
Date: 2026-10-01
Revised: 2026-10-02 (twice)
Supersedes: none
Status changed on Kapardhi's instruction, 2026-10-02 (was Proposed).

## Decision
Embedding similarity is reported **only as a continuous covariate**, as within-model ranks,
computed with **at least two encoders**, and **never compared against an absolute cutoff**.

- **It never defines a group, stratum or boundary.** Any grouping comes from construction
  (ADR-004). **No conclusion is drawn from similarity differences between adjacent construction
  levels.**
- **Calibration: each encoder is calibrated on known same-meaning pairs before its similarity is
  interpreted**, and the calibration is reported alongside the figure it qualifies. The pairs come
  from L1 construction itself, each L1 paraphrase paired with its source field, so every
  constructed benchmark carries its own calibration set. For an external dataset with no such
  pairs, the covariate is not reported. A fixed share of constructed L1 pairs (20%, chosen by
  seeded random selection at construction time) is reserved as the calibration set and is never
  used as a benchmark item. Calibration is therefore independent of every item it qualifies,
  including L1.

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
- **Adjacent construction levels are not separable by similarity.** v4 and v5 inverted under both
  encoders, by 0.000483 and 0.003926, against a per-slot p10-p90 spread of roughly 0.11. The
  post-hoc 44-pair diagnostic (below) moved the same five-point statistic from rho = -0.9 to -0.7
  on a different population of the same data, reversing the verdict. A statistic that moves that
  far on a population change cannot carry a conclusion about neighbouring levels.
- **A similarity boundary is a cutoff in different clothes**, which is why similarity now defines
  no group at all. An earlier version of this ADR allowed up to two similarity-defined strata; a
  median split would have satisfied it while reintroducing exactly the uncalibrated bar the
  no-cutoff rule exists to forbid.
- **Closed:** an earlier version drew calibration pairs from the same L1 items the covariate then
  described, so on L1 the calibration was not independent of what it qualified. The reserved 20%
  holdout closes that: calibration pairs are never benchmark items, so independence holds for
  every level including L1.

## Assumptions
- Calibration pairs come from L1 construction, so a benchmark with L1 items has them by
  construction. A benchmark with no L1 items has none, and the covariate is then unreportable.
- A 20% reserved share is enough to characterise an encoder's same-meaning scale. Untested: no
  minimum calibration-set size has been established, and on a small L1 set 20% may be too few
  pairs to read a scale from.
- Rank stability observed on paraphrase distance carries over to other similarity relations,
  including similarity to the nearest train field, which EXP-002 did not measure.
- Two encoders suffice to catch an encoder-specific artifact. Weakly tested: EXP-002's two are
  both English web-trained sentence encoders and their Cohen's kappa on the deciding call was
  0.328.

## Alternatives
- **Similarity-defined strata, of any number.** Rejected: any boundary drawn on similarity is a
  cutoff, and EXP-002 is evidence that neighbouring levels are not separable in any case.
- **Per-encoder calibrated cutoffs.** Partly adopted and partly rejected: calibration is now
  required, thresholding on it is still forbidden. Allowing the cutoff back would need an
  experiment showing a calibrated bar is stable across encoders.
- **One encoder, absolute cutoff.** What H1 did. Its verdict depends on which encoder is chosen.
- **Raw cosines, no rank, no calibration.** Honest and not comparable across items or runs.
- **Human similarity judgments.** Closest to the construct, most expensive, and needs its own
  agreement study first.

## Failure modes
- **A continuous covariate has no headline number**, so a reader may impose a threshold mentally
  where the ADR forbids one in print. The calibration reported alongside is the only defence.
- **A benchmark with no L1 items loses the covariate entirely**, which removes it silently from
  exactly the material (L2, L4) where novelty claims are strongest.
- **Calibration inherits its pairs' construction.** Same-meaning pairs define sameness by how
  they were built, so the calibration carries that definition's biases into every figure it
  qualifies. The reserved holdout buys independence, not neutrality.
- **The holdout spends benchmark material.** A fifth of constructed L1 pairs become calibration
  and are unavailable as items, so L1 sample size drops by 20% and every L1 statistic loses power
  accordingly.
- **Ranks hide magnitude** by design: two items adjacent in rank can be far apart in similarity.
- **Agreement for the wrong reason.** Encoders of one family can agree through a shared bias.
  "At least two" is a floor, and different families should be preferred.
- **Encoder contamination.** SGD has been public since 2019 and SGD-X since 2021, so both
  encoders may have seen these schemas. Rank stability could be an artifact of that.

## Consequences
- Easier: a reported covariate survives a change of encoder; no number rests on an uncalibrated
  bar; a figure arrives with the evidence for what its scale means.
- Harder: every similarity figure needs at least two encoder runs plus a calibration set.
- **H1's shape is not reusable:** a proportion clearing a cosine threshold is what the no-cutoff
  rule forbids.
- **H2's shape is partly reusable.** Comparisons across construction-defined groups are allowed,
  so a v1-against-v5 contrast stays in scope and its Wilcoxon result stands. Inference from
  adjacent groups is not allowed, so the five-point monotonicity test and the v4-against-v5
  comparison are out. Future hypotheses about similarity are written as a continuous covariate, a
  contrast across construction-defined groups, or a paired comparison.

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
