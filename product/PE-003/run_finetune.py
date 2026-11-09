"""PE-003: LoRA fine-tune on Tinker, against B3.

    # offline first: the whole pipeline against the stub backend. No key, no upload, no credits.
    uv run python run_finetune.py --csv ~/export.csv --columns ../PE-001/columns.yaml \\
        --split-assignment ../../data/product-eval/split_assignment.json \\
        --providers ../PE-002/providers.yaml --consent ../PE-002/consent.yaml --stub

    # for real, once PE-002's Gate 2 has passed on both conditions
    uv run python run_finetune.py ... --prompt-sha <sha> --gate2-metrics <PE-002 test metrics.json>

**B3 is run here rather than imported.** PE-002's test pass writes aggregates only, by design, so
its per-item correctness is not on disk to pair against — and that rule is right. So PE-003 imports
PE-002's modules and runs B3 itself, in this process, pairing internally. That also means the
baseline is **PE-002's own code** rather than a copy of it: a reimplementation that drifted would
change the baseline silently, which is worse than the cross-directory import.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
# The baseline must be PE-002's code, not a copy of it. See the module docstring.
sys.path.insert(0, str(HERE.parent / "PE-002"))

from baselines import Prediction, _norm, to_scored, vocabulary_of  # noqa: E402
from columns import Columns  # noqa: E402
from consent import Consent, ConsentError  # noqa: E402
from data import Item, apply_split, labelled, load_split_assignment, of_split, read_items  # noqa: E402
from prompts import (  # noqa: E402
    PromptFreezeError,
    PromptTemplate,
    build_prompt,
    select_fewshot,
)
from provenance import SCRIPT_VERSION, git_state, run_id, sha256_file, utc_now, write_json  # noqa: E402
from rungs import LADDER, Providers  # noqa: E402
from safety import assert_output_safe  # noqa: E402
from scoring import accuracy_of, cluster_bootstrap, paired_compare, spread  # noqa: E402

from dataset import Example, build_dataset  # noqa: E402
from sweep import run_sweep  # noqa: E402
from recipe import (  # noqa: E402
    ALPHA,
    MAX_EPOCHS,
    BASE_LR,
    LORA_RANK,
    MIN_EFFECT_PP,
    PRIMARY_SEED,
    SEEDS,
)

# PE-002's scoring module owns these; named here so the two experiments report the same interval.
BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED = 10_000, 0


def make_examples_for(items: list[Item], targets: list[Item], template: PromptTemplate,
                      vocabulary: set[str], *, with_reply: bool) -> list[Example]:
    """Training examples: B1's prompt in, the label out.

    The prompt is B1's, unchanged, so the only difference from B3 is weights versus examples. The
    completion is the action alone for the primary configuration; `--with-reply` adds the reply,
    which is the shippable shape and is reported separately.
    """
    out: list[Example] = []
    for target in targets:
        prompt = build_prompt(
            template, items=items, target=target, vocabulary=vocabulary, fewshot=None
        )
        completion = target.action.strip()
        if with_reply and target.reply.strip():
            completion = f"{completion}\nreply: {target.reply.strip()}"
        out.append(Example(target.item_id, target.conversation_id, prompt, completion))
    return out


def predictions_from(samples: list[str], targets: list[Item], vocabulary: set[str]) -> list[Prediction]:
    preds: list[Prediction] = []
    for text, target in zip(samples, targets):
        first = (text or "").strip().splitlines()[0] if (text or "").strip() else ""
        if first.lower().startswith("action:"):
            first = first.split(":", 1)[1].strip()
        preds.append(Prediction(target.item_id, target.conversation_id, target.action, first))
    return preds


def verdict(
    per_seed: dict[int, dict[str, Any]], *, primary_seed: int
) -> dict[str, Any]:
    """PE-003's pre-registered verdict: seed 0 decides, and the seeds must agree.

    Seed 0 is named in advance so the comparison cannot be picked from among three after the fact.
    If the three seeds disagree, the result reads UNSTABLE and no claim is made either way: a
    spread that can flip the answer has swamped the effect.
    """
    if primary_seed not in per_seed:
        return {"verdict": "NOT_ESTABLISHED", "reason": "no_prompted_rung_yet"}

    def passes(body: dict[str, Any]) -> bool:
        return body["difference_pp"] >= MIN_EFFECT_PP and body["p_value"] < ALPHA

    outcomes = {seed: passes(body) for seed, body in per_seed.items()}
    primary = outcomes[primary_seed]
    agreed = len(set(outcomes.values())) == 1
    if not agreed:
        label = "UNSTABLE"
    else:
        label = "PASS" if primary else "FAIL"
    return {
        "verdict": label,
        "primary_seed": primary_seed,
        "seeds_agree": agreed,
        "per_seed_passes": {str(k): v for k, v in sorted(outcomes.items())},
        "threshold_pp": MIN_EFFECT_PP,
        "alpha": ALPHA,
    }


def check_gate_two(path: Path | None) -> dict[str, Any]:
    """PE-003 is blocked by PE-002's Gate 2, both conditions. Checked, not assumed.

    Without the file the run refuses: PE-003 exists to answer "does the fine-tune beat B3", and
    that question only matters once Gate 2 has established that the task needs a language model at
    all and that there is headroom for a fine-tune to occupy.
    """
    if path is None:
        raise RuntimeError(
            "--gate2-metrics is required: PE-003 is blocked by PE-002's Gate 2, both conditions. "
            "Pass the metrics.json from PE-002's stage-2 TEST run. (--stub skips this.)"
        )
    payload = json.loads(path.read_text(encoding="utf-8"))
    gate = payload.get("gate_2") or {}
    conditions = gate.get("conditions") or {}
    failing = {k: v.get("verdict") for k, v in conditions.items() if v.get("verdict") != "PASS"}
    if gate.get("overall") != "PASS" or failing:
        raise RuntimeError(
            f"{path}: PE-002's Gate 2 did not pass ({gate.get('overall')}); "
            f"not passing: {failing}.\n"
            "If condition 1 failed, the pattern is lexical and the track ends rather than "
            "fine-tuning. If condition 2 failed, there is no headroom for a fine-tune to occupy "
            "and the claim becomes cost, latency and on-prem. If either is NOT_ESTABLISHED, the "
            "measurement it needs has not been made. Nothing has been trained."
        )
    return {"gate2_source_sha256": sha256_file(path), "gate2_overall": "PASS"}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="PE-003: LoRA fine-tune vs B3 (UPLOADS client text)")
    ap.add_argument("--csv", type=Path, required=True)
    ap.add_argument("--columns", type=Path, required=True)
    ap.add_argument("--split-assignment", type=Path, required=True)
    ap.add_argument("--providers", type=Path, required=True)
    ap.add_argument("--consent", type=Path, required=True)
    ap.add_argument("--gate2-metrics", type=Path, help="PE-002 stage-2 TEST metrics.json")
    ap.add_argument("--split", choices=("dev", "test"), default="dev")
    ap.add_argument("--prompt-dir", type=Path, default=HERE.parent / "PE-002" / "prompts")
    ap.add_argument("--prompt-sha", help="required for --split test")
    ap.add_argument("--with-reply", action="store_true", help="secondary configuration: train on action + reply")
    ap.add_argument("--base-model", default="Qwen/Qwen3.5-9B")
    ap.add_argument("--max-epochs", type=int, default=None)
    ap.add_argument("--runs-dir", type=Path, default=REPO / "runs" / "PE-003")
    ap.add_argument("--stub", action="store_true", help="offline: no key, no upload, no credits")
    args = ap.parse_args(argv)

    if not args.csv.exists():
        print(f"error: {args.csv} does not exist", file=sys.stderr)
        return 2

    cols = Columns.load(args.columns)
    items = apply_split(read_items(args.csv, cols), load_split_assignment(args.split_assignment))
    train = labelled(of_split(items, "train"))
    dev = labelled(of_split(items, "dev"))
    targets = labelled(of_split(items, args.split))
    if not train or not dev or not targets:
        print("error: the split leaves train, dev or the target split empty", file=sys.stderr)
        return 2
    vocabulary = vocabulary_of(train)

    try:
        template = PromptTemplate.load(args.prompt_dir / LADDER["B1"].prompt_file)
        template.require_pinned(args.prompt_sha, split=args.split)
    except (PromptFreezeError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 5

    gate_info: dict[str, Any] = {}
    if args.stub:
        print("NOTE: --stub, so nothing is uploaded, no consent is required and Gate 2 is not checked.")
        consent: Consent | None = None
    else:
        try:
            gate_info = check_gate_two(args.gate2_metrics)
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 8
        providers = Providers.load(args.providers)
        try:
            consent = Consent.load(args.consent)
            # Training reaches Tinker, plus whatever provider B3 runs on.
            consent.require({"tinker"} | providers.providers_reached(["B3"]))
        except ConsentError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 6

    # --- the sweep -------------------------------------------------------------------------------
    dev_prompts = [
        build_prompt(template, items=items, target=t, vocabulary=vocabulary, fewshot=None)
        for t in dev
    ]

    def make_backend(lr: float, seed: int) -> Any:
        if args.stub:
            from trainer import StubBackend

            return StubBackend(name=f"stub-lr{lr:.1e}-s{seed}")
        from trainer import TinkerBackend

        return TinkerBackend(base_model=args.base_model, rank=LORA_RANK)

    mask_totals: dict[str, Any] = {}

    def make_examples(backend: Any) -> list:
        nonlocal mask_totals
        raw = make_examples_for(items, train, template, vocabulary, with_reply=args.with_reply)
        masked, totals = build_dataset(raw, backend.tokenizer())
        mask_totals = totals
        return masked

    def evaluate_dev(_backend: Any, sampler: Any) -> float:
        preds = predictions_from(sampler.generate(dev_prompts), dev, vocabulary)
        return accuracy_of(to_scored(preds))

    sweep = run_sweep(
        make_backend,
        make_examples,
        evaluate_dev=evaluate_dev,
        max_epochs=args.max_epochs or MAX_EPOCHS,
    )

    # --- B3, run here so the comparison is paired -------------------------------------------------
    fewshot = select_fewshot(train, k=8, seed=BOOTSTRAP_SEED)
    b3_prompts = [
        build_prompt(template, items=items, target=t, vocabulary=vocabulary, fewshot=fewshot)
        for t in targets
    ]
    if args.stub:
        from trainer import StubSampler

        b3_samples = StubSampler(answer=sorted(vocabulary)[0]).generate(b3_prompts)
    else:
        entry = Providers.load(args.providers)
        b3_backend = entry.entries[entry.by_rung["B3"]].build("B3")
        b3_samples = [
            b3_backend.complete(p, constrain_to=None).text for p in b3_prompts
        ]
    b3_preds = predictions_from(b3_samples, targets, vocabulary)
    b3_scored = to_scored(b3_preds)

    # --- score the chosen LR's seeds on the target split -----------------------------------------
    target_prompts = [
        build_prompt(template, items=items, target=t, vocabulary=vocabulary, fewshot=None)
        for t in targets
    ]
    per_seed: dict[int, dict[str, Any]] = {}
    accuracies: list[float] = []
    for run in sweep.runs_at_chosen_lr():
        backend = make_backend(run.learning_rate, run.seed)
        sampler = backend.checkpoint(run.best_checkpoint)
        preds = predictions_from(sampler.generate(target_prompts), targets, vocabulary)
        scored = to_scored(preds)
        accuracies.append(accuracy_of(scored))
        per_seed[run.seed] = {
            "accuracy": round(accuracy_of(scored), 4),
            "checkpoint": run.best_checkpoint,
            "cluster_bootstrap_95": cluster_bootstrap(
                scored, accuracy_of, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED
            ),
            **paired_compare(b3_scored, scored).as_dict(),
        }

    metrics: dict[str, Any] = {
        "experiment": "PE-003",
        "split": args.split,
        "configuration": "action_and_reply" if args.with_reply else "action_only",
        "b3_accuracy": round(accuracy_of(b3_scored), 4),
        "b3_cluster_bootstrap_95": cluster_bootstrap(
            b3_scored, accuracy_of, resamples=BOOTSTRAP_RESAMPLES, seed=BOOTSTRAP_SEED
        ),
        "fine_tune_per_seed": {str(k): v for k, v in sorted(per_seed.items())},
        "fine_tune_across_seeds": spread(accuracies),
        "sweep": sweep.as_dict(),
        "verdict": verdict(per_seed, primary_seed=PRIMARY_SEED),
        "reply_metric": None,
    }
    assert_output_safe(metrics, "$metrics")

    rid = run_id(REPO)
    out_dir = args.runs_dir / rid
    config: dict[str, Any] = {
        "experiment": "PE-003",
        "run_id": rid,
        "generated_at": utc_now(),
        "script_version": SCRIPT_VERSION,
        **git_state(REPO),
        "step": "finetune",
        "split": args.split,
        "stub_mode": bool(args.stub),
        "base_model": args.base_model,
        "lora_rank": LORA_RANK,
        "base_learning_rate": BASE_LR,
        "seeds": list(SEEDS),
        "primary_seed": PRIMARY_SEED,
        "input_sha256": sha256_file(args.csv),
        "split_assignment_sha256": sha256_file(args.split_assignment),
        "columns_sha256": cols.sha256(),
        "prompt_b1_sha256": template.sha256,
        "n_train_items": len(train),
        "n_dev_items": len(dev),
        "n_eval_items": len(targets),
        # The pre-registered loss-mask totals. A run whose weighted-token count did not match its
        # completions would have stopped in dataset.py rather than reach this file.
        "loss_mask": mask_totals,
        "thresholds": {"MIN_EFFECT_PP": MIN_EFFECT_PP, "ALPHA": ALPHA, "LORA_RANK": LORA_RANK},
        **gate_info,
        **(consent.as_config() if consent else {"consent_sha256": None}),
    }
    assert_output_safe(config, "$config")

    write_json(out_dir / "metrics.json", metrics)
    write_json(out_dir / "config.json", config)

    print(f"PE-003 — {args.split} split, {metrics['configuration']}")
    print(f"  train {len(train)} items   dev {len(dev)}   {args.split} {len(targets)}")
    print(f"  loss mask: {mask_totals.get('weighted_tokens_total')} weighted of "
          f"{mask_totals.get('positions_total')} positions "
          f"({mask_totals.get('weighted_share')})")
    print(f"  LR chosen on dev: {sweep.chosen_learning_rate:.2e}  from {sweep.dev_means}")
    print(f"  B3 accuracy {metrics['b3_accuracy']:.4f}")
    for seed, body in metrics["fine_tune_per_seed"].items():
        print(
            f"  seed {seed}: accuracy {body['accuracy']:.4f}  "
            f"{body['difference_pp']:+.2f} pp vs B3  p {body['p_value']:.3g}"
        )
    v = metrics["verdict"]
    print(f"  VERDICT: {v['verdict']}  (primary seed {v.get('primary_seed')}, "
          f"seeds agree: {v.get('seeds_agree')})")
    print(f"\nwrote {out_dir / 'metrics.json'}\nwrote {out_dir / 'config.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
