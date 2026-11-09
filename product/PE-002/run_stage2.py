"""PE-002 stage 2: the model rungs B0 to B5, and the Gate 2 verdict.

    uv run python run_stage2.py --csv ~/export.csv --columns ../PE-001/columns.yaml \\
        --split-assignment ../../data/product-eval/split_assignment.json \\
        --providers providers.yaml --consent consent.yaml \\
        --split dev --rungs B1 B3

**This is the first step in the whole plan that uploads client conversation text.** It refuses to
send anything without a consent record naming every provider it would reach (the plan's Q9), and
the test split additionally requires the prompt to be pinned by hash.

Stage 1's trivial baselines are recomputed here rather than imported, so that Gate 2 condition 1 is
a genuinely paired comparison on the same items. Pass `--stage1-metrics` to cross-check the
recomputed floor against stage 1's own figure; a mismatch means the splits differ and the run
stops.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from baselines import (
    Prediction,
    _norm,
    fit_majority,
    fit_predict_lexical,
    parse_failures,
    predict_majority,
    to_scored,
    vocabulary_of,
)
from columns import Columns
from consent import Consent, ConsentError
from data import Item, apply_split, labelled, load_split_assignment, of_split, read_items
from normalize import stable_hash
from prompts import (
    PromptFreezeError,
    PromptTemplate,
    build_prompt,
    select_fewshot,
)
from provenance import SCRIPT_VERSION, git_state, run_id, sha256_file, utc_now, write_json
from rungs import LADDER, MODEL_RUNGS, Providers
from safety import assert_output_safe
from scoring import (
    accuracy_of,
    cluster_bootstrap,
    holm,
    paired_compare,
    spread,
)
from thresholds import (
    ALPHA,
    BOOTSTRAP_RESAMPLES,
    BOOTSTRAP_SEED,
    FEWSHOT_K,
    MIN_EFFECT_PP,
    RUNS_PER_RUNG,
)

REPO = Path(__file__).resolve().parents[2]


def extract_action(text: str, vocabulary: set[str]) -> str:
    """Pull the action out of a completion.

    Accepts a bare label or a JSON object with an `action` field, since B2's structured output
    returns the latter. Anything else is returned as-is and will fail the vocabulary check, which
    is the pre-registered behaviour: an output outside the vocabulary counts as **incorrect** and is
    **also** counted as a parse failure. Deliberately forgiving about the wrapper and strict about
    the label: being lenient on the label would flatter whichever rung formats worst, which is the
    thing B2 exists to measure.
    """
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError:
            return stripped
        if isinstance(payload, dict) and isinstance(payload.get("action"), str):
            return payload["action"].strip()
        return stripped
    # A single line that is exactly a known label, possibly prefixed "action:".
    for line in stripped.splitlines():
        candidate = line.strip()
        if candidate.lower().startswith("action:"):
            candidate = candidate.split(":", 1)[1].strip()
        if _norm(candidate) in vocabulary:
            return candidate
    return stripped


def run_rung(
    rung_name: str,
    *,
    providers: Providers,
    items: list[Item],
    targets: list[Item],
    train: list[Item],
    vocabulary: set[str],
    prompt_dir: Path,
    fewshot_seed: int,
) -> tuple[list[Prediction], dict[str, Any]]:
    rung = LADDER[rung_name]
    entry = providers.entries[providers.by_rung[rung_name]]
    backend = entry.build(rung_name)
    template = PromptTemplate.load(prompt_dir / rung.prompt_file)

    fewshot = (
        select_fewshot(train, k=FEWSHOT_K, seed=fewshot_seed) if rung.fewshot else None
    )
    constrain = sorted(vocabulary) if rung.constrained else None

    preds: list[Prediction] = []
    in_tok = out_tok = 0
    latencies: list[float] = []
    settings: dict[str, Any] = {}
    unsupported: list[str] = []
    for target in targets:
        prompt = build_prompt(
            template, items=items, target=target, vocabulary=vocabulary, fewshot=fewshot
        )
        completion = backend.complete(prompt, constrain_to=constrain)
        preds.append(
            Prediction(
                target.item_id,
                target.conversation_id,
                target.action,
                extract_action(completion.text, vocabulary),
            )
        )
        in_tok += completion.input_tokens
        out_tok += completion.output_tokens
        latencies.append(completion.latency_ms)
        settings = completion.settings_sent
        for flag in completion.unsupported_settings:
            if flag not in unsupported:
                unsupported.append(flag)

    n = max(1, len(targets))
    meta: dict[str, Any] = {
        "provider_ref": entry.key,
        "prompt_file": rung.prompt_file,
        "prompt_sha256": template.sha256,
        "constrained": rung.constrained,
        "fewshot_k": FEWSHOT_K if rung.fewshot else 0,
        # Hashes, not ids: the seed and the train split already determine the selection, so the
        # ids add nothing to reproducibility — and an item id from a WhatsApp export may encode a
        # phone number.
        "fewshot_item_id_hashes": [stable_hash(i.item_id) for i in fewshot] if fewshot else [],
        "input_tokens": in_tok,
        "output_tokens": out_tok,
        "cost_usd": round(entry.cost(in_tok, out_tok), 6),
        "cost_usd_per_item": round(entry.cost(in_tok, out_tok) / n, 8),
        "latency_ms_per_item": round(sum(latencies) / n, 2),
        "settings_sent": settings,
        # Pre-registered settings the provider refused. Not empty on a Claude rung: see
        # backends.py and PE-002's Change log.
        "unsupported_settings": unsupported,
    }
    return preds, meta


def score(preds: list[Prediction], vocabulary: set[str]) -> dict[str, Any]:
    scored = to_scored(preds)
    return {
        "n_items": len(scored),
        "accuracy": round(accuracy_of(scored), 4),
        "cluster_bootstrap_95": cluster_bootstrap(
            scored, accuracy_of, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED
        ),
        "parse_failures": parse_failures(preds, vocabulary),
    }


def gate_two(
    *,
    rung_scores: dict[str, dict[str, Any]],
    prompted_rungs: list[str],
    floor_name: str,
    floor_preds: list[Prediction],
    best_prompted: str | None,
    best_preds: list[Prediction] | None,
    ceiling: float | None,
) -> dict[str, Any]:
    """PE-002's two Gate 2 conditions, plus the frontier gap as a report."""
    conditions: dict[str, Any] = {}

    if best_prompted is None or best_preds is None:
        conditions["1_task_needs_a_language_model"] = {
            "verdict": "NOT_ESTABLISHED",
            "reason": "no_prompted_rung_yet",
            "threshold_pp": MIN_EFFECT_PP,
            "alpha": ALPHA,
        }
    else:
        paired = paired_compare(to_scored(floor_preds), to_scored(best_preds))
        passed = paired.difference_pp >= MIN_EFFECT_PP and paired.p_value < ALPHA
        conditions["1_task_needs_a_language_model"] = {
            "verdict": "PASS" if passed else "FAIL",
            "best_prompted_rung": best_prompted,
            "floor_rung": floor_name,
            "threshold_pp": MIN_EFFECT_PP,
            "alpha": ALPHA,
            **paired.as_dict(),
        }

    qwen_prompted = [r for r in prompted_rungs if r in rung_scores]
    best_qwen_acc = max((rung_scores[r]["accuracy"] for r in qwen_prompted), default=None)
    if ceiling is None:
        conditions["2_headroom_for_a_fine_tune"] = {
            "verdict": "NOT_ESTABLISHED",
            "reason": "no_label_noise_ceiling",
            "threshold_pp": MIN_EFFECT_PP,
        }
    elif best_qwen_acc is None:
        conditions["2_headroom_for_a_fine_tune"] = {
            "verdict": "NOT_ESTABLISHED",
            "reason": "no_prompted_rung_yet",
            "threshold_pp": MIN_EFFECT_PP,
        }
    else:
        gap_pp = (ceiling - best_qwen_acc) * 100.0
        conditions["2_headroom_for_a_fine_tune"] = {
            "verdict": "PASS" if gap_pp >= MIN_EFFECT_PP else "FAIL",
            "label_noise_ceiling_intra_rater": round(ceiling, 4),
            "best_prompted_accuracy": round(best_qwen_acc, 4),
            "headroom_pp": round(gap_pp, 2),
            "threshold_pp": MIN_EFFECT_PP,
        }

    verdicts = [c["verdict"] for c in conditions.values()]
    overall = "FAIL" if "FAIL" in verdicts else ("NOT_ESTABLISHED" if "NOT_ESTABLISHED" in verdicts else "PASS")
    return {"overall": overall, "conditions": conditions}


def _b2_constraint_check(rung_scores: dict[str, Any]) -> dict[str, Any]:
    if "B2" not in rung_scores:
        return {"verdict": "NOT_ESTABLISHED", "reason": "no_prompted_rung_yet"}
    b2 = int(rung_scores["B2"]["parse_failures"])
    b1 = int(rung_scores["B1"]["parse_failures"]) if "B1" in rung_scores else None
    if b2 > 0:
        return {"verdict": "FAIL", "b2_parse_failures": b2, "b1_parse_failures": b1}
    if b1 is not None and b1 == 0:
        # Both clean. Consistent with the constraint working, and equally with B1 never having
        # needed it, so this does not establish that the constraint applied.
        return {"verdict": "NOT_ESTABLISHED", "b2_parse_failures": b2, "b1_parse_failures": b1}
    return {"verdict": "PASS", "b2_parse_failures": b2, "b1_parse_failures": b1}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PE-002 stage 2: the model rungs (UPLOADS client text)")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--columns", type=Path, required=True)
    ap.add_argument("--split-assignment", type=Path, required=True)
    ap.add_argument("--providers", type=Path, required=True)
    ap.add_argument("--consent", type=Path, required=True, help="the Q9 record. No consent, no requests")
    ap.add_argument("--split", choices=("dev", "test"), default="dev")
    ap.add_argument("--rungs", nargs="+", default=list(MODEL_RUNGS), choices=list(MODEL_RUNGS))
    ap.add_argument("--prompt-dir", type=Path, default=Path(__file__).resolve().parent / "prompts")
    ap.add_argument("--prompt-sha", help="required for --split test: pins the B1 template")
    ap.add_argument("--runs", type=int, default=RUNS_PER_RUNG)
    ap.add_argument("--seed", type=int, default=BOOTSTRAP_SEED)
    ap.add_argument("--label-noise-ceiling", type=float, help="intra-rater agreement from PE-001's re-test")
    ap.add_argument("--stage1-metrics", type=Path, help="a stage-1 metrics.json, to cross-check the floor")
    ap.add_argument("--runs-dir", type=Path, default=REPO / "runs" / "PE-002")
    ap.add_argument("--stub", action="store_true", help="run every rung against the offline stub backend")
    args = ap.parse_args(argv)

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2

    cols = Columns.load(args.columns)
    items = apply_split(read_items(args.csv, cols), load_split_assignment(args.split_assignment))
    train = labelled(of_split(items, "train"))
    targets = labelled(of_split(items, args.split))
    if not train or not targets:
        print("error: the split assignment leaves train or the target split empty", file=sys.stderr)
        return 2
    vocabulary = vocabulary_of(train)

    providers = Providers.load(args.providers)
    missing = [r for r in args.rungs if r not in providers.by_rung]
    if missing:
        print(
            f"error: {args.providers} configures no provider for rung(s) {missing}.\n"
            "Which models B4 and B5 are is Q7 and is Kapardhi's to answer.",
            file=sys.stderr,
        )
        return 2

    # --- the two gates, before anything is sent ---------------------------------------------------
    try:
        template = PromptTemplate.load(args.prompt_dir / LADDER["B1"].prompt_file)
        template.require_pinned(args.prompt_sha, split=args.split)
    except (PromptFreezeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 5

    if args.stub:
        print("NOTE: --stub, so nothing is uploaded and no consent record is required.")
        consent: Consent | None = None
    else:
        try:
            consent = Consent.load(args.consent)
            consent.require(providers.providers_reached(args.rungs))
        except ConsentError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 6

    # --- the floor, recomputed here so condition 1 is genuinely paired ----------------------------
    majority_label = fit_majority(train)
    floor_candidates: dict[str, list[Prediction]] = {
        "B-triv-maj": predict_majority(majority_label, targets)
    }
    try:
        lex_preds, _ = fit_predict_lexical(train, targets, seed=args.seed)
        floor_candidates["B-triv-lex"] = lex_preds
    except (ImportError, ValueError):
        pass
    floor_name = max(
        floor_candidates, key=lambda k: (accuracy_of(to_scored(floor_candidates[k])), k)
    )
    floor_preds = floor_candidates[floor_name]
    floor_accuracy = round(accuracy_of(to_scored(floor_preds)), 4)

    if args.stage1_metrics:
        stage1 = json.loads(args.stage1_metrics.read_text(encoding="utf-8"))
        if abs(float(stage1.get("floor_accuracy", -1)) - floor_accuracy) > 1e-9:
            print(
                "error: the floor recomputed here does not match --stage1-metrics "
                f"({floor_accuracy} vs {stage1.get('floor_accuracy')}).\n"
                "The two runs are not on the same split or the same export. Nothing was sent.",
                file=sys.stderr,
            )
            return 7

    # --- the rungs --------------------------------------------------------------------------------
    rung_scores: dict[str, dict[str, Any]] = {}
    rung_meta: dict[str, dict[str, Any]] = {}
    best_run_preds: dict[str, list[Prediction]] = {}

    for rung_name in args.rungs:
        per_run: list[dict[str, Any]] = []
        accs: list[float] = []
        for run_index in range(args.runs):
            if args.stub:
                from backends import StubBackend

                stub = StubBackend(name=rung_name, answers={}, fallback=majority_label)
                preds = [
                    Prediction(
                        t.item_id,
                        t.conversation_id,
                        t.action,
                        stub.complete("", constrain_to=sorted(vocabulary)).text,
                    )
                    for t in targets
                ]
                meta = {
                    "provider_ref": "stub",
                    "prompt_sha256": template.sha256,
                    "cost_usd": 0.0,
                    "cost_usd_per_item": 0.0,
                    "latency_ms_per_item": 0.0,
                    "settings_sent": {"backend": "stub"},
                    "unsupported_settings": [],
                    "fewshot_item_id_hashes": [],
                }
            else:
                preds, meta = run_rung(
                    rung_name,
                    providers=providers,
                    items=items,
                    targets=targets,
                    train=train,
                    vocabulary=vocabulary,
                    prompt_dir=args.prompt_dir,
                    fewshot_seed=args.seed + run_index,
                )
            scored = score(preds, vocabulary)
            per_run.append({"run": run_index, **{k: scored[k] for k in ("accuracy", "parse_failures")}})
            accs.append(scored["accuracy"])
            if run_index == 0:
                best_run_preds[rung_name] = preds
                rung_scores[rung_name] = scored
                rung_meta[rung_name] = meta
        # CLAUDE.md: mean and spread over >=3 runs whenever a model is sampled. A rung whose spread
        # exceeds its distance to a neighbour has not separated from it.
        rung_scores[rung_name]["across_runs"] = spread(accs)
        rung_scores[rung_name]["per_run"] = per_run

    prompted = [r for r in ("B1", "B2", "B3") if r in rung_scores]
    best_prompted = max(prompted, key=lambda r: rung_scores[r]["accuracy"]) if prompted else None

    # Secondary pairings: every rung against every other, Holm-corrected, no claim attached.
    secondary: dict[str, float] = {}
    names = list(rung_scores)
    for i, a in enumerate(names):
        for b in names[i + 1 :]:
            secondary[f"{a}_vs_{b}"] = paired_compare(
                to_scored(best_run_preds[a]), to_scored(best_run_preds[b])
            ).p_value

    metrics: dict[str, Any] = {
        "experiment": "PE-002",
        "stage": "stage_2",
        "split": args.split,
        "floor_rung": floor_name,
        "floor_accuracy": floor_accuracy,
        "rungs": rung_scores,
        "gate_2": gate_two(
            rung_scores=rung_scores,
            prompted_rungs=prompted,
            floor_name=floor_name,
            floor_preds=floor_preds,
            best_prompted=best_prompted,
            best_preds=best_run_preds.get(best_prompted) if best_prompted else None,
            ceiling=args.label_noise_ceiling,
        ),
        "secondary_pairings_holm": holm(secondary),
        # B2 is B1 plus a constraint. If a backend accepts `response_format` and ignores it — which
        # is possible on an OpenAI-COMPATIBLE endpoint rather than OpenAI itself, and is not
        # something the response tells us — then B2 is B1 under another name and nothing else here
        # would show it. The tell is parse failures: a constrained rung cannot emit an
        # out-of-vocabulary answer, so B2 having any, or having as many as B1, means the constraint
        # did not apply. Reported, never thresholded.
        "b2_constraint_check": _b2_constraint_check(rung_scores),
        "reply_metric": None,
    }
    assert_output_safe(metrics, "$metrics")

    rid = run_id(REPO)
    out_dir = args.runs_dir / rid
    config: dict[str, Any] = {
        "experiment": "PE-002",
        "run_id": rid,
        "generated_at": utc_now(),
        "script_version": SCRIPT_VERSION,
        **git_state(REPO),
        "step": "stage_2",
        "split": args.split,
        "seed": args.seed,
        "runs_per_rung": args.runs,
        "rungs_run": list(args.rungs),
        "stub_mode": bool(args.stub),
        "input_sha256": sha256_file(args.csv),
        "split_assignment_sha256": sha256_file(args.split_assignment),
        "columns_sha256": cols.sha256(),
        "prompt_b1_sha256": template.sha256,
        "n_train_items": len(train),
        "n_eval_items": len(targets),
        "rung_meta": rung_meta,
        "thresholds": {"MIN_EFFECT_PP": MIN_EFFECT_PP, "ALPHA": ALPHA, "FEWSHOT_K": FEWSHOT_K},
        **providers.as_config(),
        **(consent.as_config() if consent else {"consent_sha256": None}),
    }
    assert_output_safe(config, "$config")

    write_json(out_dir / "metrics.json", metrics)
    write_json(out_dir / "config.json", config)

    print(f"PE-002 stage 2 — {args.split} split, {args.runs} run(s) per rung")
    print(f"  floor {floor_name} at {floor_accuracy}")
    for name, s in rung_scores.items():
        cb = s["cluster_bootstrap_95"]
        print(
            f"  {name:<4} accuracy {s['accuracy']:.4f}  cluster 95% [{cb['lo']}, {cb['hi']}]"
            f"  spread {s['across_runs']['stdev']:.4f}  parse failures {s['parse_failures']}"
            f"  ${rung_meta.get(name, {}).get('cost_usd_per_item', 0):.6f}/item"
        )
    g = metrics["gate_2"]
    print(f"  GATE 2: {g['overall']}")
    for cond, body in g["conditions"].items():
        print(f"    {body['verdict']:<16} {cond}")
    print(f"\nwrote {out_dir / 'metrics.json'}\nwrote {out_dir / 'config.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
