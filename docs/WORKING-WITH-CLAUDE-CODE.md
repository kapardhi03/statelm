# Working with Claude Code on StateLM

This is your guide, not Claude's. Claude Code reads `CLAUDE.md`; you read this.

## Who does what

| | Research chat (claude.ai Project) | Claude Code (your repo) |
|---|---|---|
| Role | Research architect + reviewer | Research engineer |
| Decides | Research question, ADRs, benchmark design, what an experiment must show | Nothing about direction |
| Produces | Decisions, ADR text, experiment designs, critiques | Code, data tooling, runs, numbers, handoff notes |
| Source of truth | `docs/research/` in the repo | `docs/research/` in the repo |

The repo's `docs/research/` folder is the bridge. Decisions made in the chat get written there.
Results produced by Claude Code get written there. Neither side keeps state anywhere else.

## The loop

1. **Decide in the research chat.** Settle the decision, the experiment design, and the metric.
2. **Write it into the repo.** Either paste the updated ADR / experiment text yourself, or ask
   Claude Code to apply it (it will prompt you before touching ADRs, the research question, or
   the architecture file, because those are `ask` rules in `.claude/settings.json`).
3. **Implement in Claude Code.** Sessions start in plan mode. Read its plan, push back, approve.
4. **Record.** `/record-result EXP-NNN <run-id>` fills Result + Interpretation and runs the
   reviewer subagent.
5. **Hand off.** `/handoff` writes a summary to `docs/research/handoffs/` and prints it.
6. **Paste the handoff into the research chat.** Review it there, fill the Decision, update
   ADRs and STATE.md. Back to step 1.

## Setup (once)

```bash
cd statelm
git init && git add -A && git commit -m "Scaffold StateLM research repo"
claude
```

Inside Claude Code:

1. Run `/context` and confirm `CLAUDE.md`, `STATE.md`, and the data rule are listed under memory
   files (the data rule appears only after Claude reads a matching file).
2. Paste the comprehension check below. If its answer is wrong, fix `CLAUDE.md` before doing
   any work.

### Comprehension check prompt

```text
Before we start: read CLAUDE.md, docs/research/STATE.md and
docs/research/research-question.md. Then tell me, in under 10 bullets:
1. what you are and are not allowed to decide,
2. which ADRs are Proposed and what that means for your work,
3. the five things you must keep distinct,
4. which experiment you could start today without any pending decision, and why.
Do not edit anything.
```

## Daily habits that matter

- **Plan mode is the default.** `Shift+Tab` cycles modes; prefixing a prompt with `/plan` plans
  one request. Don't approve a plan you haven't read.
- **One experiment per session.** `/clear` between unrelated tasks. Long sessions drift.
- **Interrupt early.** If the plan or first edit goes the wrong way, press `Esc` and redirect.
  Correcting late costs more than correcting early.
- **Ask it to interview you** when a task is underspecified, instead of letting it guess.
- **Use the reviewer after every result:** "Use the research-reviewer subagent on EXP-002."
- **Commit after every step.** Checkpoints help, but git is your real undo.
- **When it repeats a mistake twice, add a line to `CLAUDE.md`.** That's what the file is for.

## Guardrails already configured

| Guardrail | Where | What it does |
|---|---|---|
| Plan mode by default | `.claude/settings.json` | No edits without an approved plan |
| Test split blocked | `.claude/settings.json` deny | Claude's file tools can't read or write `data/splits/test/` |
| Research files need approval | `.claude/settings.json` ask | Prompts you before ADR, research question, or architecture edits |
| Leakage rules | `.claude/rules/data-and-splits.md` | Loads when Claude touches data code |
| Reviewer | `.claude/agents/research-reviewer.md` | Read-only adversarial check of results |

The test-split block is a guardrail, not a guarantee. A Python script Claude runs can still read
those files. Evaluation scripts need to, which is fine; just never ask Claude to print test items.
Because Claude's file tools are blocked there, **you** run the script that creates the test split.

## Prompt templates

### Start an experiment

```text
/new-experiment EXP-002 schema-novelty-audit
```
(EXP-002 already has a record; for it, skip straight to "Implement".)

### Implement an experiment

```text
Implement EXP-002 exactly as specified in
docs/research/experiments/EXP-002-schema-novelty-audit.md.
Start with the sanity check (reproduce the ~65% slot-name overlap). If it doesn't reproduce,
stop and report before doing anything else.
Write code in experiments/EXP-002/, outputs in runs/EXP-002/<run-id>/.
Write tests for the overlap and similarity functions.
Plan first. List any assumption you'd have to make that the experiment file doesn't cover.
```

### Bring in a decision from the research chat

```text
The research chat accepted ADR-003 with this change: <paste>.
Update docs/research/adr/ADR-003-typed-abstention.md and STATE.md accordingly.
Change nothing else.
```

### Ask for an honest status

```text
What in this repo currently depends on a Proposed ADR as if it were Accepted?
List files and lines. Don't fix anything.
```

## What to paste back into the research chat

Always the `/handoff` output. If a number surprised you, paste the relevant `metrics.json` too.
Don't summarize results from memory; paste the file.
