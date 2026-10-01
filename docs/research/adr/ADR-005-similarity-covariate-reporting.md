# ADR-005: Embedding similarity is reported as a rank or stratum, never against a cutoff

Status: Proposed
Date: 2026-10-01
Supersedes: none

## Decision
Embedding similarity is reported as a **within-model rank or stratum**, computed with **at least
two encoders**, **never compared against an absolute cutoff**, and **no conclusion is drawn from
adjacent strata**.

This governs how the covariate ADR-004 mandates is reported. It does not change ADR-004: novelty
levels still come from construction, and similarity still assigns nothing.

## Why
EXP-002 measured the same quantity two ways and the two disagreed in one axis and agreed in the
other, which is what this ADR encodes.

- **An absolute cutoff is not comparable across encoders.** At the same cosine 0.8, H1's rate was
  12.20% under all-MiniLM-L6-v2 and 41.46% under bge-base-en-v1.5. Worse, the cutoff's meaning
  differs by encoder geometry: of known same-slot paraphrases, 41.9% fall below 0.8 under MiniLM
  against 5.6% under BGE (v1), rising to 69.4% against 26.2% at v5. Under MiniLM the bar was
  stricter than a genuine paraphrase of the same slot.
- **Ranks are reproducible where cutoffs are not.** In H2 both encoders produced the same
  Spearman rho to the digit, with the inversion in the same place, while their absolute means sat
  0.08 to 0.10 apart throughout. Ordering survived the change of encoder; the cutoff did not.
- **Adjacent strata are not separable.** v4 and v5 inverted under both encoders, by 0.000483 and
  0.003926, against a per-slot spread of roughly 0.11 from p10 to p90. Gaps three orders of
  magnitude below the spread they come from are not measured differences.

## Assumptions
- Two encoders are enough to catch an encoder-specific artifact. Weakly tested: EXP-002's two are
  both English web-trained sentence encoders, and their Cohen's kappa on the deciding call was
  0.328, so they are not independent in any strong sense.
- Rank stability observed on SGD-X paraphrase distance carries over to other similarity relations,
  including similarity to the nearest train field, which EXP-002 did not measure.
- The claims the benchmark makes do not require distinguishing adjacent strata. If one ever does,
  this ADR forbids it and a new experiment would be needed.

## Alternatives
- **Per-encoder calibrated cutoffs.** Calibrate each encoder against a reference distribution,
  such as known paraphrases, then threshold. Closest viable alternative; needs its own experiment
  to set and validate the reference, and EXP-002 pre-registered no such calibration.
- **One encoder, absolute cutoff.** What H1 did. Its verdict depends on which encoder is chosen,
  which is the finding above.
- **Raw cosines, no rank and no threshold.** Honest but not comparable across items or runs.
- **Human similarity judgments.** Closest to the construct and the most expensive; would need its
  own inter-annotator agreement study before use.

## Failure modes
- **Ranks hide magnitude.** Two items adjacent in rank can be far apart in similarity, and this
  reporting rule conceals that by design.
- **Agreement for the wrong reason.** Two encoders of one family can agree because they share a
  bias, not because the rank is real. "At least two" is a floor, not a guarantee, and encoders
  from different families should be preferred.
- **Strata boundaries are a cutoff in disguise** if they are set on similarity values. This ADR
  does not settle whether strata come from construction or from quantiles of the reported
  distribution, and that gap should be closed before strata are used in a claim.
- **Encoder contamination.** SGD has been public since 2019 and SGD-X since 2021, so both
  encoders may have seen these schemas in pretraining. Rank stability could itself be an artifact
  of that, and nothing in EXP-002 rules it out.

## Consequences
- Easier: a reported covariate survives a change of encoder, and no number rests on an
  uncalibrated bar.
- Harder: every similarity figure needs at least two encoder runs, and no binary "near-duplicate
  or not" is available any more. A hypothesis cannot be written as a proportion clearing a cosine
  threshold, which means **H1's own form is not reusable under this ADR**. Future hypotheses about
  similarity have to be written about ranks, strata, or paired comparisons.

## Evidence
- EXP-002 H1, run `20261001T180031Z-746c803`: 12.20% against 41.46% at the same cutoff; the
  paraphrase calibration reference showing the cutoff is stricter than a same-slot paraphrase
  under one of the two encoders.
- EXP-002 H2, same run: identical Spearman rho across encoders with the inversion in the same
  place, absolute means 0.08 to 0.10 apart, v4/v5 inverted under both.
- Not evidence for this ADR: similarity to the nearest train field, which is the relation ADR-004
  stratifies by and which EXP-002 did not measure. ADR-005 generalizes from paraphrase distance
  to that relation without having tested it.
