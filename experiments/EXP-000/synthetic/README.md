# EXP-000 synthetic conversation set (`exp000-synthetic-v1`)

20 invented WhatsApp-style real-estate sales conversations, 164 turns, customer and seller.
Written by Claude Code (`claude-opus-5`) on 2026-10-03 at Kapardhi's instruction, after the v2
census showed the real corpus cannot support the abstention hypothesis.

Every record carries `provenance.source = "synthetic"`, `provenance.generator = "claude-opus-5"`
and `provenance.labeler = null`.

## What this set is for, and the limit that cannot be engineered away

**Agreement measured on these conversations is not evidence for ADR-003.**

ADR-003 assumes humans can reliably distinguish the three abstention types *in real
conversations*. These conversations were written by a model that knows the taxonomy and wrote
the annotation guideline, so they instantiate the categories more cleanly than a real chat does.
κ here measures whether two people can apply the guideline to text authored against it. That is
worth knowing — it tests the instrument — and it is a different question.

`knowns-unknowns.md` already carries the risk this is an instance of: *"Synthetic-data
circularity: same frontier model as generator, baseline, and judge."*

Accordingly:

- `agreement.py --manifest` reports the real and synthetic subsets separately. The synthetic
  verdict is labelled **"guideline usability, not evidence for ADR-003"** in the printed report,
  in `metrics.json` and in the experiment record. Kapardhi's decision, 2026-10-03.
- No sheet shows which subset an item came from. The source lives in the sampler's manifest and
  nowhere else, so the labels are blind to it.

## Do not read the conversations before labelling

Kapardhi is Annotator A. Reading `syn_*.jsonl` before labelling turns his labels into recall of
the text rather than a judgement about it, and the agreement that follows would measure memory.
The Run book says this at the sampling step too.

This README is safe to read: it describes provenance and limits, and maps no phenomenon to any
conversation.

## What is deliberately not here

- **No labels.** Not in the records, not in a sidecar, not in a filename.
- **No intended-label notes**, and no hint of what any turn is meant to exercise. File names are
  `syn_001` to `syn_020`, in no meaningful order.
- **No phenomenon clustered per conversation.** Grouping one phenomenon per file would label by
  position as surely as a label column would.

The set does contain material the sampler's cues cannot fully see, including code-mixed Telugu
and Hindi forms beyond the lists added on 2026-10-03. That is intentional: a turn the cues miss
is still labellable, and the gap between what the cues find and what the set contains is itself
worth measuring.
