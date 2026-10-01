# Architectural Decision Records

## Rules
- Status values: **Proposed**, **Accepted**, **Rejected**, **Superseded by ADR-NNN**.
- Never change an ADR's status unless Kapardhi explicitly instructs it, naming the ADR and
  the new status. Record "Status changed on Kapardhi's instruction, <date>" in the ADR.
- Claude Code may draft new ADRs, always with status Proposed.
- Never edit an Accepted ADR's decision. Supersede it with a new ADR.
- Nothing may be built on a Proposed ADR as if it were Accepted.

## Template

```markdown
# ADR-NNN: <title>

Status: Proposed
Date: YYYY-MM-DD
Supersedes: none

## Decision
## Why
## Assumptions
## Alternatives
## Failure modes
## Consequences
## Evidence
(experiment IDs or literature rows; "none yet" is allowed and honest)
```
