"""Pre-registered values for PE-003: the LoRA recipe and the verdict thresholds.

Named `recipe.py` rather than `thresholds.py`, which is what PE-001 and PE-002 call theirs, for a
mechanical reason worth stating: PE-003 puts PE-002's directory on `sys.path` so the B3 baseline is
**PE-002's own code rather than a copy of it**, and two bare modules of the same name cannot both
be imported. PE-002's `thresholds` is the one on the path; this file is the one PE-003 reads.

That collision is the cost of the cross-directory import, and it is the smaller cost: a
reimplemented B3 that drifted from PE-002's would change the baseline silently, which is worse than
one renamed file. The promote-to-a-shared-module question EXP-003 raised is now plainly live for
this pair, and it is still Kapardhi's.


Approved by Kapardhi on 2026-11-09 ("approved, write the code"), before any code existed, as
`docs/product/evals/PE-003-lora-fine-tune.md` records. Under CLAUDE.md rule 2 none of them moves
after a result has been seen; a change and its reason go in that record's Change log.
"""

from __future__ import annotations

# --- the LoRA recipe ------------------------------------------------------------------------------
# Tinker trains LoRA only and exposes `rank`; target modules are not configurable, and its LoRA
# primer settles that question anyway ("LoRA performs better when applied to all weight matrices…
# attention-only LoRA underperforms even when we match the number of trainable parameters").
#
# NOT SWEPT. At a 64-item train split rank 32 carries about 10,100x the capacity Tinker's own
# sizing rule asks for, and even rank 1 carries ~316x: rank is not the knob for fitting this data.
# Whether it is a knob for overfitting it is what the dev-set early stopping is for.
LORA_RANK = 32

# The docs' most emphasised failure mode is porting a full-fine-tune learning rate to LoRA. The
# cookbook's get_lora_lr_over_full_finetune_lr returns 10, which is applied to the full-FT figure
# below. The product of the two is what actually reaches the optimizer, and the run config records
# all three numbers so a reader does not have to multiply.
FULL_FINETUNE_LR = 1e-5
LORA_LR_MULTIPLIER = 10.0
BASE_LR = FULL_FINETUNE_LR * LORA_LR_MULTIPLIER

# The one hyperparameter the docs call most important, so the one thing swept: the figure above,
# and it times and divided by three. Selected on DEV, never on test.
LR_SWEEP_FACTORS = (1 / 3, 1.0, 3.0)

# The docs: LoRA is less tolerant of large batch sizes than full fine-tuning, and raising the rank
# does not fix it.
BATCH_SIZE = 8

MAX_EPOCHS = 10
EARLY_STOPPING_PATIENCE = 2       # evaluations without a dev improvement
SEEDS = (0, 1, 2)                 # CLAUDE.md: mean and spread whenever a model is trained
PRIMARY_SEED = 0                  # named in advance, so the comparison cannot be picked from three

# $0.10 per GB per month otherwise, and an untidied adapter store is a running cost for nothing.
CHECKPOINT_TTL_SECONDS = 14 * 24 * 3600

# --- the verdict ----------------------------------------------------------------------------------
# PE-002's figure and the plan's §3.2's: at a ~200-item test split, +10 pp is detected about four
# times in five and +5 pp at no reachable size.
MIN_EFFECT_PP = 10.0
ALPHA = 0.05

# Sampling at evaluation time. Temperature IS settable on Tinker, unlike on a Claude rung.
EVAL_TEMPERATURE = 0.0
EVAL_MAX_TOKENS = 256
