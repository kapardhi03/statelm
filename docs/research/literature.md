# Prior Work and What It Means for StateLM

Rule: no claim of novelty may contradict a row below. Add a row before citing a new paper.

| Work | What it establishes | Consequence for us |
|---|---|---|
| SGD (Rastogi et al. 2020) | Schema-in-prompt DST with unseen services in test | Schema conditioning is not novel |
| SGD-X (Lee et al. 2022, arXiv 2110.06800) | Top BERT/T5 trackers lose 12–18% JGA from schema rewording alone. 65% of slot names and 71% of intent names in "unseen" test schemas exactly match train names. Variants v1–v5 are ordered by increasing distance from the original schemas. Exact wording under "Verified quotes" below | "Unseen" must be defined and overlap measured per item (EXP-002) |
| Coca et al. 2023 (arXiv 2303.09905) | Synthetic schema paraphrases improve SGD-X robustness | Augmentation baseline for L1 novelty |
| SOM-DST (Kim et al. 2020, arXiv 1911.03906) | State as memory: CARRYOVER / DELETE / DONTCARE / UPDATE ops + value generation | Delta formulation is not novel. Rare ops are the hard part (DELETE F1 far below UPDATE) |
| FnCTOD (Li et al. 2024, arXiv 2402.10466) | Fine-tuned 13B LLaMA2-Chat reaches ChatGPT-level zero-shot DST via function calling | Small-ish models doing DST is not novel. Our size range must go below 7B |
| LDST (Feng et al. 2023) | Instruction-tuned smaller open models match ChatGPT on DST, motivated by privacy and self-hosting | "Self-hostable" is not a novel motivation |
| GoLLIE (Sainz et al. 2024, arXiv 2310.03668) | Guideline-following fine-tuning generalizes to unseen extraction schemas | Strong analog for schema-description conditioning |
| Vehicle function calls (arXiv 2609.09476) | Schema-in-prompt vs fine-tuned keys for 270M–1.7B SLMs, single-turn, no state | Excludes dialogue history and changing state: our territory |
| LongMemEval (Wu et al. 2025, arXiv 2410.10813) | Memory benchmark incl. knowledge updates and abstention, measured via QA | Abstention there = info absent (the easy case) |
| **MemOps (Hao et al. 2026, arXiv 2607.12893)** | Memory as explicit ops (remember / forget / update / reflect) with old/new value and evidence spans. Ordered trajectory reconstruction is fragile even for strong models | **Closest neighbor.** Schema-free, frontier + 27B only, GPT-4o judge, synthetic (55% retention). Supports ADR-002 |
| Sun et al. 2024 (arXiv 2409.09629) | Compares softmax, token-score, verbalized confidence for DST; fine-tuning improves calibration | Confidence for DST is not novel |
| **"Lost with a Map" (arXiv 2609.33883)** | Conversational-state representations in schema-aware TOD; State–Action Controller with structural abstention thresholds | **Unread. Must read before any gap claim.** |

## Verified quotes

Quoted from the source PDF rather than from memory or a secondary summary. Retrieved 2026-10-01
from arXiv:2110.06800v3 (23 Aug 2022), "SGD-X: A Benchmark for Robust Generalization in
Schema-Guided Dialogue Systems", Lee, Gupta, Rastogi, Cao, Zhang, Wu.

### The 65% / 71% figures (Introduction)

> The uniformity of SGD is evident in its schema element names. Of the names in the test set
> schemas "unseen" in the train set, 71% of intent names and 65% of slot names exactly match
> names appearing in the train schemas, meaning most names in "unseen" schemas are actually
> already seen by the model during training.

On the unit: the sentence says "the names in the test set schemas" and does not state whether a
name occurring in several unseen services counts once or once per service. EXP-002 fixed
`(service, slot)` instances as primary before running. That reading reproduces both figures
(64.66% and 71.43%); the unique-name reading reproduces neither (57.29% and 70.37%). The
ambiguity is the paper's, the choice was ours and pre-registered, and the evidence favours it.

### How the paraphrases were produced (Dataset Construction)

> For SGD-X, we crowdsourced paraphrases across 400+ authors from Amazon Mechanical Turk. We
> chose crowdsourcing over automatic paraphrasing methods because we found that automatic
> methods were often semantically inaccurate and provided insufficient linguistic diversity

> At the end of the collection and vetting phase, we had at least 5 paraphrases for every name
> and description. When there were more than 5, we selected 5 at random.

> Designing the tasks, collecting data, manually vetting responses, and composing the variants
> took approximately 1 month.

This is what supports calling the variants human-written and human-vetted. Note the random
selection among surplus paraphrases: adjacent variants need not be separated by a consistent
margin, which bears on EXP-002's H2.

### Variant ordering, v1 to v5 (Composing Schema Variants)

> We placed paraphrases into schema variants such that variants increasingly diverge from the
> original schemas as the variant number increases.

> After sorting, for every schema element elem, we obtained a list of unique name paraphrases
> N^elem = [n^elem_idx], idx in {1..5}, ordered by increasing Levenshtein distance from the
> original name n^elem_gt. Similarly for every schema element description, we obtained a list of
> unique description paraphrases D^elem = [d^elem_idx], idx in {1..5}, ordered by increasing
> Jaccard distance from the original description d^elem_gt.

> This establishes the SGD-X benchmark as a series of increasingly challenging evaluation sets.
> Henceforth in this paper, we refer to these schema variants as v1 through v5, where v1 refers
> to the variant schema closest to the original and v5 the farthest.

Measured, Table 1 ("SGD-X dataset statistics"):

| Metric | Orig | v1 | v2 | v3 | v4 | v5 | Avg |
|---|---|---|---|---|---|---|---|
| % of test slot names seen in train | 65% | 13% | 14% | 5% | 6% | 2% | 8% |
| % of test intent names seen in train | 71% | 0% | 0% | 4% | 0% | 4% | 2% |
| Levenshtein distance (names) | – | 0.30 | 0.42 | 0.49 | 0.56 | 0.61 | 0.48 |
| BLEU (descriptions) | – | 18.8 | 11.3 | 5.6 | 2.9 | 1.0 | 7.9 |

Two consequences for EXP-002's H2. The ordering is established, but on **surface** metrics:
Levenshtein distance over names and Jaccard distance over descriptions, sorted independently per
schema element. A monotone trend in embedding space is therefore not guaranteed by construction,
which is what makes H2 falsifiable rather than circular. And the paper's own surface statistic is
not monotone across variants (13%, 14%, 5%, 6%, 2%: v2 above v1, v4 above v3), so a strict
monotonicity test on a mean can fail even where the construction ordering holds in its own metric.

## Reading queue
1. arXiv 2609.33883 ("Lost with a Map"): full read, add findings above
2. MemOps full paper: data generation pipeline, failure taxonomy
3. LongMemEval-V2 (May 2026): agentic memory, check for schema conditioning
