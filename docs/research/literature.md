# Prior Work and What It Means for StateLM

Rule: no claim of novelty may contradict a row below. Add a row before citing a new paper.

| Work | What it establishes | Consequence for us |
|---|---|---|
| SGD (Rastogi et al. 2020) | Schema-in-prompt DST with unseen services in test | Schema conditioning is not novel |
| SGD-X (Lee et al. 2022, arXiv 2110.06800) | Top BERT/T5 trackers lose 12–18% JGA from schema rewording alone. Of names in test schemas for services unseen in train, 71% of intent names and 65% of slot names exactly match train names (definition used by the EXP-002 gate) | "Unseen" must be defined and overlap measured per item (EXP-002) |
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

## Reading queue
1. arXiv 2609.33883 ("Lost with a Map"): full read, add findings above
2. MemOps full paper: data generation pipeline, failure taxonomy
3. LongMemEval-V2 (May 2026): agentic memory, check for schema conditioning
