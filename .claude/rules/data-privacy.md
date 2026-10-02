# Data privacy

This file has no `paths` frontmatter on purpose: it applies to every session, whatever files
that session touches.

- **Client conversation text never leaves Kapardhi's machine.** It is never requested, read,
  committed or uploaded, scrubbed or not. Do not ask him to paste a conversation, an excerpt, a
  single message, or a scrubbed sample.
- **Tools that touch client text run locally.** EXP-000's scrubber, item sampler,
  annotation-sheet generator and agreement script all run on his machine. Only aggregates —
  counts, Cohen's κ, confusion matrices — go into `runs/`.
- **`data/raw/` and `data/scrubbed/` are never read by Claude's file tools.** Both are
  gitignored and both are denied to `Read` and `Edit` in `.claude/settings.json`. Scrubbed text
  is still client text.

If a task appears to need conversation text, it is the task that is wrong. Say so and stop.
