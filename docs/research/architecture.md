# Architecture (current agreed system)

This file shows only what has been decided or formally proposed. It is not a wish list.
Every diagram node must trace to an ADR or to `research-question.md`.

Status: everything below is **Proposed** until ADR-001..003 are accepted.

## 1. System Architecture (v0.1, problem level)

```mermaid
flowchart TD
    subgraph X["Inputs X_t (available at inference)"]
        H["Dialogue history H_1..t<br/>speaker + timestamp per turn"]
        S["Schema S<br/>field names, types, descriptions"]
        Z0["Prior state Z_t-1<br/>derived from ledger, never raw model text"]
    end
    H --> M["StateLM<br/>size bound TBD, proposed ≤4B"]
    S --> M
    Z0 --> M
    M --> D{"Per field in S:<br/>evidence in turn t?"}
    D -- "no evidence" --> NOOP["NO-OP<br/>implicit, not abstention"]
    D -- "evidence, value determinable" --> OPS["Delta ops<br/>ADD / UPDATE / RETRACT<br/>+ evidence span + confidence"]
    D -- "evidence, value not determinable" --> ABS["ABSTAIN<br/>insufficient / ambiguous / conflicting"]
    OPS --> L["Deterministic ledger<br/>append-only, versioned, NOT learned"]
    ABS --> L
    L --> Z1["Current state Z_t"]
    L --> HIST["Field lineage<br/>supersession chain"]
    Z1 -. "becomes Z_t-1 next turn" .-> Z0
    OPS --> E["Evaluation vs gold Y_t"]
    ABS --> E
    HIST --> E
```

## 2. Training / Data Pipeline

Not drawn. Depends on Stage 2 (X, Y) and Stage 3 (data model). Drawing it now would invent decisions.

## 3. Evaluation Pipeline

Not drawn. Depends on Stage 4 (benchmark). Known requirement: evaluate with both gold and
predicted prior state Z_t-1 to measure exposure bias (ADR-002 failure mode).

## 4. Research Experiment Flow (stage gates)

```mermaid
flowchart TD
    RQ["Research question v1<br/>interaction claim"] --> LIT["Literature positioning<br/>SGD-X, SOM-DST, FnCTOD, LDST,<br/>LongMemEval, MemOps, Sun 2024"]
    LIT --> E0["EXP-000: Label feasibility<br/>can humans agree on abstention types?"]
    LIT --> E2["EXP-002: Schema novelty audit<br/>is 'unseen' measurable?"]
    E0 --> G0{"Agreement acceptable?"}
    G0 -- "no" --> R0["Merge or redefine<br/>abstention taxonomy"]
    R0 --> E0
    G0 -- "yes" --> E1["EXP-001: Headroom probe<br/>frontier vs small zero-shot, pilot set"]
    E2 --> E1
    E1 --> G1{"Where is the gap?"}
    G1 -- "frontier also fails" --> P1["Benchmark-led contribution"]
    G1 -- "frontier solves, small fails" --> P2["Small-model contribution"]
    G1 -- "both solve it" --> P3["Claim too weak:<br/>harden conditions or pivot"]
    P3 --> RQ
    P1 --> NEXT["Stage 2: define X, Y, data model"]
    P2 --> NEXT
```
