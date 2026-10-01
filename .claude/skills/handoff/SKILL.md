---
name: handoff
description: Write a handoff summary of this session's work for the separate research-architect conversation. Use at the end of a work session.
disable-model-invocation: true
---

Recent commits:
!`git log --oneline -15 2>/dev/null || echo "(no git history)"`

Uncommitted changes:
!`git status --short 2>/dev/null || echo "(not a git repo)"`

Write `docs/research/handoffs/<YYYY-MM-DD>-<short-topic>.md` and print it in full in chat so
Kapardhi can paste it into the research conversation. Keep it under 60 lines. Use this structure:

```markdown
# Handoff: <date> · <topic>

## Done
- What was built or run, with experiment IDs and file paths

## Results (numbers only)
- Metric, value, baseline value, n, seeds, run ID

## Deviations from plan
- Anything done differently from the experiment record, and why

## Assumptions I made
- Every judgment call not covered by docs/research/, so the research chat can accept or reject it

## Things that look wrong or weak
- Suspected leakage, surprising numbers, assumptions that now look shaky

## Decisions needed (human)
- Questions only the human or research chat can answer

## Proposed next step
- One concrete next step, tied to an experiment ID
```

Rules: no adjectives like "great", "promising", "strong". No claims beyond the numbers.
