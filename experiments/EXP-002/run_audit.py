"""EXP-002 Steps 2 and 3: H1, H2, and the exploratory frequency breakdown.

Refuses to run unless the Step 1 gate passed: the gate is a pre-condition for every number
here, so the audit reads the gate run's `sanity_check.json` and stops if `gate.pass` is not
true rather than trusting the operator to remember.

H1  Among unseen-service slots with no exact (N0) name match in train, the share whose nearest
    train slot clears cosine 0.8 under BOTH models, each model judged on its own nearest
    neighbour. Supported at >= 50%.
H2  Covariate validity. All five SGD-X variants are L1 by construction (ADR-004); nothing is
    selected by a measurement. Supported only if, under BOTH models, (a) a one-sided paired
    Wilcoxon signed-rank test puts v5 below v1 at p < 0.01 and (b) Spearman rho between variant
    index and per-variant mean cosine is <= -0.9.

Usage:
    uv run python run_audit.py \
        --data-root ../../data/raw/sgd/<commit> --dataset-commit <commit> --gate-run <run-id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import measures
import overlap
import schemas
import similarity
import thresholds

EXPERIMENT = "EXP-002"
STEP = "steps-2-3-h1-h2"
DATASET_REPO = "https://github.com/google-research-datasets/dstc8-schema-guided-dialogue"


def git_output(*args: str) -> str:
    return subprocess.run(
        ["git", *args], capture_output=True, text=True, check=True, cwd=Path(__file__).parent
    ).stdout.strip()


def variant_schema_path(data_root: Path, idx: int) -> Path:
    return data_root / "sgd_x" / "data" / f"v{idx}" / "test" / "schema.json"


def require_gate_passed(gate_dir: Path) -> dict:
    path = gate_dir / "sanity_check.json"
    if not path.exists():
        raise SystemExit(f"no gate result at {path}; run run_sanity_check.py first")
    gate = json.loads(path.read_text(encoding="utf-8"))
    if gate.get("gate", {}).get("pass") is not True:
        raise SystemExit(f"gate did not pass in {path}; EXP-002 stops at Step 1 by design")
    return gate


def validate_variants(
    original: tuple[schemas.Service, ...], variants: dict[int, tuple[schemas.Service, ...]]
) -> dict:
    """H2's 1:1 pairing depends on structure, so check it and stop loudly if it fails.

    SGD-X appends the variant index to every service name (`Alarm_1` -> `Alarm_11` in v1), so
    the pairing key is the ORIGINAL service name with that suffix stripped, plus slot position.
    """
    report = {}
    for idx, services in sorted(variants.items()):
        problems = []
        if len(services) != len(original):
            problems.append(f"{len(services)} services against {len(original)} originals")
        else:
            for orig, var in zip(original, services):
                expected = f"{orig.name}{idx}"
                if var.name != expected:
                    problems.append(f"expected service {expected!r}, found {var.name!r}")
                elif len(var.slots) != len(orig.slots):
                    problems.append(
                        f"{orig.name}: {len(var.slots)} slots against {len(orig.slots)}"
                    )
        report[f"v{idx}"] = {"ok": not problems, "problems": problems}
        if problems:
            raise SystemExit(
                f"SGD-X v{idx} does not line up with the original schemas, so the 1:1 slot "
                f"pairing H2 needs is invalid: {problems[:5]}"
            )
    return report


def slot_texts(slots) -> list[str]:
    return [similarity.embedding_input(s.name, s.description) for s in slots]


def run_h1(embedders, train_slots, h1_slots) -> tuple[dict, list[dict]]:
    """Nearest train slot per H1 slot, per model, plus the agreement measures."""
    train_keys = [(s.service, s.name) for s in train_slots]
    per_model: dict[str, list[tuple[tuple, float]]] = {}
    for embedder in embedders:
        train_vecs = embedder.encode(slot_texts(train_slots))
        query_vecs = embedder.encode(slot_texts(h1_slots))
        per_model[embedder.name] = similarity.nearest(query_vecs, train_vecs, train_keys)

    names = [e.name for e in embedders]
    clears = {n: [c >= thresholds.COSINE_THRESHOLD for _, c in per_model[n]] for n in names}
    both = [all(clears[n][i] for n in names) for i in range(len(h1_slots))]
    rate = 100.0 * sum(both) / len(both)

    train_names = [s.name for s in train_slots]
    jaccard_rows = [overlap.nearest_by_jaccard(s.name, train_names) for s in h1_slots]
    jaccard_clears = [score >= thresholds.JACCARD_THRESHOLD for _, score in jaccard_rows]

    agreement_top1 = 100.0 * sum(
        per_model[names[0]][i][0] == per_model[names[1]][i][0] for i in range(len(h1_slots))
    ) / len(h1_slots)

    rows = []
    for i, slot in enumerate(h1_slots):
        for name in names:
            key, cos = per_model[name][i]
            rows.append(
                {
                    "section": "h1",
                    "model": name,
                    "service": slot.service,
                    "slot": slot.name,
                    "nearest_train_service": key[0],
                    "nearest_train_slot": key[1],
                    "cosine": round(cos, 6),
                    "clears_cosine_threshold": bool(cos >= thresholds.COSINE_THRESHOLD),
                    "nearest_train_slot_by_jaccard": jaccard_rows[i][0],
                    "jaccard": round(jaccard_rows[i][1], 6),
                }
            )

    result = {
        "population": "unseen-service slots with no N0 exact name match in train",
        "n": len(h1_slots),
        "nearest_neighbour_search_space": "all train (service, slot) instances",
        "search_space_n": len(train_slots),
        "both_models_clear_cosine_rate_percent": round(rate, 4),
        "threshold_percent": thresholds.H1_MIN_RATE,
        "supported": bool(rate >= thresholds.H1_MIN_RATE),
        "per_model_clear_rate_percent": {
            n: round(100.0 * sum(clears[n]) / len(clears[n]), 4) for n in names
        },
        "per_model_mean_nearest_cosine": {
            n: round(float(np.mean([c for _, c in per_model[n]])), 6) for n in names
        },
        "per_model_cosine_quantiles": {
            n: {
                q: round(float(np.quantile([c for _, c in per_model[n]], v)), 6)
                for q, v in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9))
            }
            for n in names
        },
        "jaccard_clear_rate_percent": round(
            100.0 * sum(jaccard_clears) / len(jaccard_clears), 4
        ),
        "agreement": {
            "top1_identity_rate_percent": round(agreement_top1, 4),
            "cohen_kappa_on_cosine_decision": round(
                measures.cohen_kappa(clears[names[0]], clears[names[1]]), 6
            ),
        },
    }
    return result, rows


def run_h2(embedders, original, variants) -> tuple[dict, list[dict]]:
    """Paired cosine of every variant slot to its own original, per variant, per model."""
    pairs = []  # (orig_service_name, position, orig_slot, {idx: variant_slot})
    for position_service, orig in enumerate(original):
        for j, orig_slot in enumerate(orig.slots):
            by_variant = {idx: variants[idx][position_service].slots[j] for idx in thresholds.VARIANTS}
            pairs.append((orig.name, j, orig_slot, by_variant))

    per_model: dict[str, dict[int, np.ndarray]] = {}
    for embedder in embedders:
        orig_vecs = embedder.encode(slot_texts([p[2] for p in pairs]))
        per_variant = {}
        for idx in thresholds.VARIANTS:
            var_vecs = embedder.encode(slot_texts([p[3][idx] for p in pairs]))
            per_variant[idx] = similarity.paired_cosine(var_vecs, orig_vecs)
        per_model[embedder.name] = per_variant

    models = {}
    for name, per_variant in per_model.items():
        means = [float(np.mean(per_variant[idx])) for idx in thresholds.VARIANTS]
        stat, p = measures.wilcoxon_lower(per_variant[5], per_variant[1])
        rho, rho_p = measures.spearman_against_index(means)
        cond_a = bool(p < thresholds.H2_WILCOXON_ALPHA)
        cond_b = bool(thresholds.spearman_meets_bound(rho))
        models[name] = {
            "mean_cosine_by_variant": {f"v{idx}": round(m, 6) for idx, m in zip(thresholds.VARIANTS, means)},
            "cosine_quantiles_by_variant": {
                f"v{idx}": {
                    q: round(float(np.quantile(per_variant[idx], v)), 6)
                    for q, v in (("p10", 0.1), ("p50", 0.5), ("p90", 0.9))
                }
                for idx in thresholds.VARIANTS
            },
            "condition_a_wilcoxon_v5_below_v1": {
                "statistic": round(stat, 6),
                "p_value": p,
                "alpha": thresholds.H2_WILCOXON_ALPHA,
                "holds": cond_a,
            },
            "condition_b_spearman_index_vs_mean": {
                "rho": rho,
                "rho_6dp": round(rho, 6),
                "p_value": rho_p,
                "max_rho": thresholds.H2_SPEARMAN_MAX,
                "float_tolerance": thresholds.H2_SPEARMAN_TOLERANCE,
                "holds": cond_b,
                # Recorded because at the boundary this differs from `holds`: one adjacent
                # inversion is rho = -0.9 in exact arithmetic but -0.8999999999999998 computed.
                "would_hold_without_float_tolerance": bool(rho <= thresholds.H2_SPEARMAN_MAX),
                "adjacent_inversions": measures.adjacent_inversions(means),
            },
            "supported": cond_a and cond_b,
            "reported_non_deciding": {
                "strictly_decreasing_means": measures.strictly_decreasing(means),
            },
        }

    rows = []
    for name, per_variant in per_model.items():
        for i, (service, position, orig_slot, by_variant) in enumerate(pairs):
            for idx in thresholds.VARIANTS:
                rows.append(
                    {
                        "section": "h2",
                        "model": name,
                        "variant": f"v{idx}",
                        "original_service": service,
                        "position": position,
                        "original_slot": orig_slot.name,
                        "variant_slot": by_variant[idx].name,
                        "cosine_to_own_original": round(float(per_variant[idx][i]), 6),
                    }
                )

    result = {
        "population": "every slot of every service in each variant test schema, paired 1:1 "
        "with its own original slot",
        "n_slot_pairs": len(pairs),
        "pairing_key": "(original service_name with the variant-index suffix stripped, slot position)",
        "per_model": models,
        "supported": all(m["supported"] for m in models.values()),
    }
    return result, rows


def run_exploratory(unseen_slots, train_slots) -> dict:
    """POST-HOC, EXPLORATORY. No hypothesis, no threshold, decides nothing."""
    train_by_name: dict[str, set[str]] = defaultdict(set)
    for slot in train_slots:
        train_by_name[slot.name].add(slot.service)
    matched = [s for s in unseen_slots if s.name in train_by_name]
    instances = Counter(s.name for s in matched)
    services: dict[str, set[str]] = defaultdict(set)
    for slot in matched:
        services[slot.name].add(slot.service)
    table = [
        {
            "name": name,
            "unseen_service_instances": count,
            "distinct_unseen_services": len(services[name]),
            "distinct_train_services": len(train_by_name[name]),
        }
        for name, count in sorted(instances.items(), key=lambda kv: (-kv[1], kv[0]))
    ]
    return {
        "label": "EXPLORATORY, POST-HOC. No hypothesis, no threshold. Chosen after the Step 1 "
        "gate result was seen, and may not be reported as support for or against H1, H2 or "
        "any ADR.",
        "matched_instances": len(matched),
        "distinct_shared_names": len(table),
        "frequency_table": table,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="EXP-002 Steps 2 and 3")
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--dataset-commit", required=True)
    parser.add_argument("--gate-run", required=True, help="run-id of the Step 1 gate run")
    parser.add_argument("--out-root", type=Path, default=Path("../../runs/EXP-002"))
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    here = Path(__file__).parent
    resolve = lambda p: p if p.is_absolute() else (here / p).resolve()
    data_root, out_root = resolve(args.data_root), resolve(args.out_root)

    gate = require_gate_passed(out_root / args.gate_run)

    np.random.seed(args.seed)
    git_commit = git_output("rev-parse", "HEAD")
    run_id = args.run_id or f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}-{git_commit[:7]}"
    run_dir = out_root / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    train_path, test_path = data_root / "train" / "schema.json", data_root / "test" / "schema.json"
    train = schemas.load_schema(train_path)
    test = schemas.load_schema(test_path)
    variants = {idx: schemas.load_schema(variant_schema_path(data_root, idx)) for idx in thresholds.VARIANTS}
    validation = validate_variants(test, variants)

    _, unseen = schemas.partition_test_services(train, test)
    train_slots = list(schemas.all_slots(train))
    unseen_slots = list(schemas.all_slots(unseen))
    flags = overlap.match_flags([s.name for s in unseen_slots], [s.name for s in train_slots], pipeline="N0")
    h1_slots = [slot for slot, matched in zip(unseen_slots, flags) if not matched]
    if not h1_slots:
        raise SystemExit("H1 population is empty; nothing to measure")

    print(f"loading {len(thresholds.EMBEDDING_MODELS)} embedding models...", flush=True)
    embedders = [similarity.SentenceTransformerEmbedder(m) for m in thresholds.EMBEDDING_MODELS]
    for e in embedders:
        print(f"  {e.name} @ {e.revision}", flush=True)

    print(f"H1 over {len(h1_slots)} slots against {len(train_slots)} train slots...", flush=True)
    h1, h1_rows = run_h1(embedders, train_slots, h1_slots)
    print("H2 over 5 variants...", flush=True)
    h2, h2_rows = run_h2(embedders, test, variants)
    exploratory = run_exploratory(unseen_slots, train_slots)

    files_read = {
        "train/schema.json": schemas.sha256_file(train_path),
        "test/schema.json": schemas.sha256_file(test_path),
        **{
            f"sgd_x/data/v{idx}/test/schema.json": schemas.sha256_file(variant_schema_path(data_root, idx))
            for idx in thresholds.VARIANTS
        },
    }
    config = {
        "experiment": EXPERIMENT,
        "step": STEP,
        "run_id": run_id,
        "gate_run_id": args.gate_run,
        "gate_slot_rate_percent": gate["gate"]["slots"]["rate_percent"],
        "git_commit": git_commit,
        "git_tree_dirty": bool(git_output("status", "--porcelain")),
        "seed": args.seed,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "dataset": {"repo_url": DATASET_REPO, "commit": args.dataset_commit, "files_read": files_read},
        "normalization": {"version": overlap.NORMALIZATION_VERSION, "h1_population_pipeline": "N0"},
        "embedding_models": [{"name": e.name, "revision": e.revision} for e in embedders],
        "input_template": thresholds.EMBEDDING_INPUT_TEMPLATE,
        "input_template_hash": hashlib.sha256(
            thresholds.EMBEDDING_INPUT_TEMPLATE.encode("utf-8")
        ).hexdigest(),
        "thresholds": {
            "cosine": thresholds.COSINE_THRESHOLD,
            "jaccard": thresholds.JACCARD_THRESHOLD,
            "h1_min_rate_percent": thresholds.H1_MIN_RATE,
            "h2_wilcoxon_alpha": thresholds.H2_WILCOXON_ALPHA,
            "h2_spearman_max_rho": thresholds.H2_SPEARMAN_MAX,
            "h2_spearman_float_tolerance": thresholds.H2_SPEARMAN_TOLERANCE,
        },
        "notes": [
            "The >= 3 seeds convention does not apply: nothing is trained or sampled and the "
            "pipeline is deterministic given pinned model revisions. The robustness axes are "
            "2 embedding models x 5 SGD-X variants.",
            "No novelty level is assigned anywhere in this run (ADR-004).",
        ],
    }
    metrics = {
        "experiment": EXPERIMENT,
        "step": STEP,
        "run_id": run_id,
        "sgd_x_structural_validation": validation,
        "h1": h1,
        "h2": h2,
        "exploratory_post_hoc": exploratory,
    }

    (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    with (run_dir / "per_slot.jsonl").open("w", encoding="utf-8") as fh:
        for row in h1_rows + h2_rows:
            fh.write(json.dumps(row) + "\n")

    lines = [
        f"{EXPERIMENT} {STEP} run {run_id}",
        f"gate run {args.gate_run} passed; dataset commit {args.dataset_commit}",
        f"models: " + ", ".join(f"{e.name}@{e.revision[:8]}" for e in embedders),
        "",
        f"H1  n={h1['n']}  both models clear cosine {thresholds.COSINE_THRESHOLD}: "
        f"{h1['both_models_clear_cosine_rate_percent']:.2f}% "
        f"(>= {thresholds.H1_MIN_RATE}% -> {'SUPPORTED' if h1['supported'] else 'REFUTED'})",
        "    per model: " + ", ".join(f"{k}={v:.2f}%" for k, v in h1["per_model_clear_rate_percent"].items()),
        f"    top-1 identity agreement {h1['agreement']['top1_identity_rate_percent']:.2f}%, "
        f"kappa {h1['agreement']['cohen_kappa_on_cosine_decision']:.3f}",
        "",
        f"H2  {h2['n_slot_pairs']} slot pairs per variant",
    ]
    for name, m in h2["per_model"].items():
        means = ", ".join(f"{k}={v:.4f}" for k, v in m["mean_cosine_by_variant"].items())
        lines += [
            f"    {name}",
            f"      means: {means}",
            f"      (a) wilcoxon v5<v1 p={m['condition_a_wilcoxon_v5_below_v1']['p_value']:.3g} "
            f"holds={m['condition_a_wilcoxon_v5_below_v1']['holds']}",
            f"      (b) spearman rho={m['condition_b_spearman_index_vs_mean']['rho']:.4f} "
            f"holds={m['condition_b_spearman_index_vs_mean']['holds']}",
            f"      strictly decreasing (reported only): {m['reported_non_deciding']['strictly_decreasing_means']}",
            f"      model verdict: {'SUPPORTED' if m['supported'] else 'REFUTED'}",
        ]
    lines += ["", f"H2 overall: {'SUPPORTED' if h2['supported'] else 'REFUTED'}"]
    report = "\n".join(lines)
    (run_dir / "log.txt").write_text(report + "\n", encoding="utf-8")
    print("\n" + report)
    print(f"\nwrote {run_dir}/config.json, metrics.json, per_slot.jsonl, log.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
