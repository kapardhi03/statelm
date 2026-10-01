# StateLM

Open research project: can a small, self-hostable language model track conversational state on
schemas it has not seen before, preserve changes over time, and explicitly abstain when the
information is ambiguous or insufficient?

Sales/CRM is the first application. The underlying problem is general conversational state
tracking.

**Status:** Stage 1 (problem definition). No model yet. See `docs/research/STATE.md`.

## Layout

```
docs/research/          research source of truth
  STATE.md              one-page current state
  research-question.md  question, definitions, hypotheses, (non-)contributions
  literature.md         prior work and what it means for this project
  architecture.md       current agreed diagrams (Mermaid)
  knowns-unknowns.md    risks, open questions, research clusters
  adr/                  architectural decision records
  experiments/          one record per experiment, pre-registered
  handoffs/             session summaries
docs/WORKING-WITH-CLAUDE-CODE.md   how this repo is developed with Claude Code
experiments/EXP-NNN/    code per experiment
src/statelm/            shared library code
data/                   raw data and frozen splits (gitignored)
runs/                   run outputs (gitignored)
```

## Principles

- Every experiment names the decision it informs, and its metric is written before it runs.
- Gold labels come from humans. Model output is never a gold label.
- Nothing is called novel without a literature row it is distinguished from.
