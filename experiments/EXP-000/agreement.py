#!/usr/bin/env python3
"""EXP-000 annotation agreement. Runs locally.

Reads two filled annotation sheets and reports Cohen's kappa overall and per category, a
confusion matrix, and value agreement, against the threshold pre-registered in EXP-000's record.

Four things this script will not do:

- **Guess whether it is measuring inter- or intra-annotator agreement.** The mode comes from
  which flag you use, never from a default, and it appears in every line of output and every
  file written. `--sheets` is two annotators; `--passes` is one annotator twice.
- **Hide a thin category.** A category with fewer than ten items is reported with its counts
  and marked not interpretable. It is never dropped, and the hypothesis is reported as
  unevaluable rather than passed when an abstention type rests on too few items.
- **Put anything but aggregates in `runs/`.** Kappas, intervals, counts and the confusion
  matrix go there. Item ids, labels per item and values go to the gitignored disagreement list
  under `data/scrubbed/`, and the script refuses to write that list anywhere else.
- **Fill Result, Interpretation or Decision.** It prints a verdict against the pre-registered
  threshold. What that verdict means is a human's to write.

    python agreement.py --sheets sheet_annotator_1.csv sheet_annotator_2.csv
    python agreement.py --passes pass_1.csv pass_2.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import platform
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import kappa
import safety
import thresholds
import values

EXPERIMENT = "EXP-000"
REQUIRED_COLUMNS = ("item_id", "conversation_id", "field", "label", "value")

INTER, INTRA = "inter_annotator", "intra_annotator"
MODE_TITLES = {INTER: "INTER-ANNOTATOR", INTRA: "INTRA-ANNOTATOR"}

#: Printed and recorded for --passes. The script cannot check either condition from a CSV, so
#: it says so rather than implying the fallback was applied correctly.
INTRA_CONDITIONS = (
    "Intra-annotator agreement requires the relabel to come at least a week later and to be "
    "blind to the first labels (EXP-000, Note on solo annotation). Neither condition is "
    "verifiable from these sheets; both are the operator's to guarantee."
)


class AgreementError(Exception):
    pass


# ---------------------------------------------------------------- loading and alignment


def load_sheet(path: str | Path) -> dict[str, dict]:
    """Read a filled sheet into {item_id: row}. Refuses anything it cannot trust."""
    path = Path(path).expanduser().resolve()
    if not path.is_file():
        raise AgreementError(f"{path} is not a file")
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        header = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in header]
        if missing:
            raise AgreementError(
                f"{path.name} is missing required column(s): {', '.join(missing)}. "
                f"Found: {', '.join(header) or '(no header)'}")
        rows: dict[str, dict] = {}
        for line, row in enumerate(reader, start=2):
            item_id = (row.get("item_id") or "").strip()
            if not item_id:
                raise AgreementError(f"{path.name} line {line}: empty item_id")
            if item_id in rows:
                raise AgreementError(
                    f"{path.name} line {line}: item_id {item_id!r} appears twice. "
                    "A duplicated item makes the pairing ambiguous; de-duplicate the sheet.")
            if not (row.get("conversation_id") or "").strip():
                raise AgreementError(
                    f"{path.name} line {line}: item {item_id!r} has no conversation_id, which "
                    "the primary bootstrap needs as its resampling unit.")
            rows[item_id] = row
    if not rows:
        raise AgreementError(f"{path.name} has a header but no rows")
    return rows


def _check_labels(name: str, rows: dict[str, dict]) -> None:
    unknown: list[str] = []
    for item_id, row in rows.items():
        label = (row.get("label") or "").strip()
        if label and label not in thresholds.LABELS:
            unknown.append(f"{item_id}: {label!r}")
    if unknown:
        shown = "\n  ".join(unknown[:10])
        more = f"\n  ... and {len(unknown) - 10} more" if len(unknown) > 10 else ""
        raise AgreementError(
            f"{name} contains {len(unknown)} label(s) outside the vocabulary:\n  {shown}{more}\n"
            f"Allowed: {', '.join(thresholds.LABELS)}. A typo scored as its own category would "
            "change every kappa, so this is an error rather than a warning.")


def align(sheet_a: dict[str, dict], sheet_b: dict[str, dict], *,
          names: tuple[str, str], allow_partial: bool) -> tuple[list[dict], dict]:
    """Pair the two sheets on item_id. Returns (items, report).

    Items where either sheet has an empty label are excluded and counted: an unfinished sheet
    should not quietly shrink n.
    """
    _check_labels(names[0], sheet_a)
    _check_labels(names[1], sheet_b)

    only_a = sorted(set(sheet_a) - set(sheet_b))
    only_b = sorted(set(sheet_b) - set(sheet_a))
    if (only_a or only_b) and not allow_partial:
        raise AgreementError(
            f"the two sheets do not cover the same items: {len(only_a)} only in {names[0]}, "
            f"{len(only_b)} only in {names[1]}. Pass --allow-partial-overlap to measure on the "
            f"{len(set(sheet_a) & set(sheet_b))} shared items, which will be recorded as the n.")

    shared = sorted(set(sheet_a) & set(sheet_b))
    if not shared:
        raise AgreementError("the two sheets share no item_id; nothing can be compared")

    items, unlabelled, conflicting_conversation = [], [], []
    for item_id in shared:
        row_a, row_b = sheet_a[item_id], sheet_b[item_id]
        label_a = (row_a.get("label") or "").strip()
        label_b = (row_b.get("label") or "").strip()
        if not label_a or not label_b:
            unlabelled.append(item_id)
            continue
        conversation_a = row_a["conversation_id"].strip()
        conversation_b = row_b["conversation_id"].strip()
        if conversation_a != conversation_b:
            conflicting_conversation.append(item_id)
            continue
        items.append({
            "item_id": item_id,
            "conversation_id": conversation_a,
            "field": (row_a.get("field") or "").strip(),
            "label_a": label_a,
            "label_b": label_b,
            "value_a": row_a.get("value") or "",
            "value_b": row_b.get("value") or "",
        })

    if conflicting_conversation:
        raise AgreementError(
            f"{len(conflicting_conversation)} item(s) carry different conversation_ids in the "
            f"two sheets, e.g. {conflicting_conversation[0]}. The sheets are not two views of "
            "the same sample; re-generate them from one sampler run.")
    if not items:
        raise AgreementError(
            f"all {len(shared)} shared items have an empty label in at least one sheet; "
            "nothing to measure")

    report = {
        "n_items_compared": len(items),
        "n_conversations": len({item["conversation_id"] for item in items}),
        "items_only_in_sheet_a": len(only_a),
        "items_only_in_sheet_b": len(only_b),
        "items_excluded_unlabelled": len(unlabelled),
        "partial_overlap_allowed": bool(allow_partial),
    }
    return items, report


# ---------------------------------------------------------------- measurement


def _intervals(pairs, clusters, statistic, *, seed, resamples) -> dict:
    """The primary interval plus the secondary one, each named by its resampling unit."""
    out = {"primary_unit": thresholds.BOOTSTRAP_UNIT_PRIMARY}
    for unit in thresholds.BOOTSTRAP_UNITS:
        out[f"ci_{unit}"] = kappa.bootstrap_ci(
            pairs, clusters, statistic, unit=unit, resamples=resamples, seed=seed,
            level=thresholds.BOOTSTRAP_CI_LEVEL,
            max_undefined_fraction=thresholds.UNDEFINED_REPLICATE_MAX_FRACTION)
    return out


def measure(items: list[dict], *, seed: int, resamples: int) -> dict:
    """Every number this script reports. Aggregates only: no item ids, no labels per item."""
    pairs = [(item["label_a"], item["label_b"]) for item in items]
    clusters = [item["conversation_id"] for item in items]

    overall_kappa = kappa.cohen_kappa(pairs)
    overall = {
        "kappa": overall_kappa,
        "percent_agreement": kappa.percent_agreement(pairs),
        "kappa_undefined_reason": None if overall_kappa is not None else (
            "expected agreement is 1: both raters used a single identical label, so kappa has "
            "no defined value"),
        **_intervals(pairs, clusters, kappa.cohen_kappa, seed=seed, resamples=resamples),
    }

    per_category = {}
    for label in thresholds.LABELS:
        counts = kappa.category_counts(pairs, label)
        value = kappa.one_vs_rest_kappa(pairs, label)
        interpretable = counts["n_either"] >= thresholds.MIN_CATEGORY_N and value is not None
        if counts["n_either"] < thresholds.MIN_CATEGORY_N:
            reason = (f"n_either {counts['n_either']} < {thresholds.MIN_CATEGORY_N}; "
                      "reported for completeness, not interpretable")
        elif value is None:
            reason = "expected agreement is 1; kappa has no defined value for this category"
        else:
            reason = None
        per_category[label] = {
            "kappa": value,
            "is_abstention_type": label in thresholds.ABSTENTION_TYPES,
            "interpretable": interpretable,
            "reason": reason,
            **counts,
            **_intervals(pairs, clusters, lambda p, l=label: kappa.one_vs_rest_kappa(p, l),
                         seed=seed, resamples=resamples),
        }

    value_pairs = [(item["value_a"], item["value_b"]) for item in items
                   if item["label_a"] == "VALUE" and item["label_b"] == "VALUE"]
    value_clusters = [item["conversation_id"] for item in items
                      if item["label_a"] == "VALUE" and item["label_b"] == "VALUE"]
    value_agreement = {
        "n_both_value": len(value_pairs),
        "primary_normalization": thresholds.VALUE_NORMALIZATION_PRIMARY,
    }
    for normalization in thresholds.VALUE_NORMALIZATIONS:
        def proportion(subset, normalization=normalization):
            if not subset:
                return None
            matches = sum(1 for a, b in subset if values.agree(a, b, normalization=normalization))
            return matches / len(subset)
        value_agreement[normalization] = {
            "agreement": proportion(value_pairs),
            "n": len(value_pairs),
            **(_intervals(value_pairs, value_clusters, proportion, seed=seed,
                          resamples=resamples) if value_pairs else {}),
        }

    return {
        "overall": overall,
        "per_category": per_category,
        "confusion_matrix": {
            "labels": list(thresholds.LABELS),
            "rows_are": "sheet_a",
            "columns_are": "sheet_b",
            "counts": kappa.confusion_matrix(pairs, thresholds.LABELS),
        },
        "label_use": {
            "sheet_a": dict(Counter(a for a, _ in pairs)),
            "sheet_b": dict(Counter(b for _, b in pairs)),
        },
        "value_agreement": value_agreement,
    }


#: What each subset's verdict is allowed to be read as. Kapardhi's decision, 2026-10-03.
SUBSET_NOTES = {
    "real": thresholds.REAL_VERDICT_NOTE,
    "synthetic": thresholds.SYNTHETIC_VERDICT_NOTE,
    "combined": thresholds.COMBINED_VERDICT_NOTE,
}


def load_item_sources(path: str | Path) -> dict[str, str]:
    """Read the sampler manifest's item -> source map.

    The map lives in the manifest because no sheet carries a source column: the annotators are
    blind to which items are synthetic, which is what makes the two subsets comparable at all.
    """
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    sources = raw.get("item_source")
    if not sources:
        raise AgreementError(
            f"{path}: no 'item_source' map. It is written by sample_items.py when a "
            "--synthetic set is sampled; a manifest from an earlier run will not have it.")
    return {str(k): str(v) for k, v in sources.items()}


def verdict(per_category: dict, *, subset: str = "combined") -> dict:
    """Apply the pre-registered threshold to the three abstention types, and nothing else."""
    rows, below, unevaluable = {}, [], []
    for label in thresholds.ABSTENTION_TYPES:
        entry = per_category[label]
        if not entry["interpretable"]:
            state = "NOT INTERPRETABLE"
            unevaluable.append(label)
        elif thresholds.meets_threshold(entry["kappa"]):
            state = "MEETS"
        else:
            state = "BELOW"
            below.append(label)
        rows[label] = {"verdict": state, "kappa": entry["kappa"],
                       "n_either": entry["n_either"], "reason": entry["reason"]}

    if unevaluable:
        hypothesis = "cannot be evaluated"
        because = (f"{', '.join(unevaluable)} rest(s) on fewer than "
                   f"{thresholds.MIN_CATEGORY_N} items")
    elif below:
        hypothesis = "refuted by the pre-registered rule"
        because = f"{', '.join(below)} below {thresholds.KAPPA_THRESHOLD}"
    else:
        hypothesis = "not refuted by the pre-registered rule"
        because = (f"all {len(thresholds.ABSTENTION_TYPES)} abstention types at or above "
                   f"{thresholds.KAPPA_THRESHOLD}")

    return {
        "subset": subset,
        "reads_as": SUBSET_NOTES.get(subset, SUBSET_NOTES["combined"]),
        "bears_on_adr_003": subset == thresholds.ADR_003_SUBSET,
        "threshold": thresholds.KAPPA_THRESHOLD,
        "threshold_source": "EXP-000 Metric section",
        "threshold_tolerance": thresholds.KAPPA_TOLERANCE,
        "applies_to": list(thresholds.ABSTENTION_TYPES),
        "per_abstention_type": rows,
        "hypothesis": hypothesis,
        "because": because,
        "note": ("A verdict against a pre-registered threshold is not a Result. Result, "
                 "Interpretation and Decision in the experiment record are a human's to fill."),
    }


# ---------------------------------------------------------------- outputs


def disagreements(items: list[dict]) -> list[dict]:
    """Label disagreements, plus value mismatches where both raters chose VALUE.

    Both values are included for a value mismatch because the item id alone cannot tell you
    whether the two annotators disagreed or just typed the figure differently. This is why the
    list is confined to the gitignored tree.
    """
    out = []
    for item in items:
        if item["label_a"] != item["label_b"]:
            out.append({
                "kind": "label",
                "item_id": item["item_id"],
                "conversation_id": item["conversation_id"],
                "field": item["field"],
                "label_a": item["label_a"],
                "label_b": item["label_b"],
            })
        elif item["label_a"] == "VALUE" and not values.agree(
                item["value_a"], item["value_b"],
                normalization=thresholds.VALUE_NORMALIZATION_PRIMARY):
            out.append({
                "kind": "value",
                "item_id": item["item_id"],
                "conversation_id": item["conversation_id"],
                "field": item["field"],
                "label_a": item["label_a"],
                "label_b": item["label_b"],
                "value_a": item["value_a"],
                "value_b": item["value_b"],
                "agrees_under_number_aware": values.agree(
                    item["value_a"], item["value_b"],
                    normalization=thresholds.VALUE_NORMALIZATION_SECONDARY),
            })
    return out


def write_disagreements(path: Path, rows: list[dict], *, mode: str, run_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {
        "_warning": "Item ids, both labels, and both values for value mismatches. Client-derived"
                    " content: this file stays in data/scrubbed/, which is gitignored.",
        "agreement_type": mode,
        "run_id": run_id,
        "disagreements": len(rows),
    }
    with path.open("w", encoding="utf-8") as handle:
        for record in (header, *rows):
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def git_output(*args: str) -> str:
    try:
        return subprocess.run(("git", *args), capture_output=True, text=True,
                              check=True, cwd=Path(__file__).parent).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def sha256_file(path: Path) -> str:
    import hashlib
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def build_config(*, mode: str, run_id: str, seed: int, resamples: int,
                 sheet_paths: tuple[Path, Path], report: dict) -> dict:
    return {
        "experiment": EXPERIMENT,
        "step": "agreement",
        "agreement_type": mode,
        "run_id": run_id,
        "git_commit": git_output("rev-parse", "HEAD"),
        "git_tree_dirty": bool(git_output("status", "--porcelain")),
        "seed": seed,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "model_name": None,
        "model_revision": None,
        "prompt_template_hash": None,
        "inputs": {
            "sheet_a": {"name": sheet_paths[0].name, "sha256": sha256_file(sheet_paths[0])},
            "sheet_b": {"name": sheet_paths[1].name, "sha256": sha256_file(sheet_paths[1])},
        },
        "alignment": report,
        "thresholds": {
            "kappa_threshold": thresholds.KAPPA_THRESHOLD,
            "kappa_tolerance": thresholds.KAPPA_TOLERANCE,
            "min_category_n": thresholds.MIN_CATEGORY_N,
            "abstention_types": list(thresholds.ABSTENTION_TYPES),
            "undefined_replicate_max_fraction": thresholds.UNDEFINED_REPLICATE_MAX_FRACTION,
            "hedged_rule": thresholds.HEDGED_RULE,
        },
        "bootstrap": {
            "resamples": resamples,
            "ci_level": thresholds.BOOTSTRAP_CI_LEVEL,
            "primary_unit": thresholds.BOOTSTRAP_UNIT_PRIMARY,
            "secondary_unit": thresholds.BOOTSTRAP_UNIT_SECONDARY,
            "method": "percentile",
        },
        "value_normalizations": {
            "primary": thresholds.VALUE_NORMALIZATION_PRIMARY,
            "secondary": thresholds.VALUE_NORMALIZATION_SECONDARY,
        },
        "notes": [
            "No model is involved, so model_name, model_revision and prompt_template_hash are "
            "null. The convention's fields are kept rather than omitted so a reader can see "
            "they were considered.",
            "The >=3 seeds convention does not apply: nothing is trained. The bootstrap is "
            "seeded and the seed is recorded.",
            "ADR-003 (typed abstention) was Proposed when these numbers were pre-registered. "
            "EXP-000 is the experiment that tests it.",
            thresholds.HEDGED_RULE_TEXT,
            *( [INTRA_CONDITIONS] if mode == INTRA else [] ),
        ],
    }


def _fmt(value, width=5, places=3) -> str:
    return f"{value:>{width}.{places}f}" if isinstance(value, (int, float)) else f"{'-':>{width}}"


def _fmt_ci(entry) -> str:
    if not entry or entry.get("low") is None:
        return "[    -,     -]"
    mark = "" if entry.get("interpretable") else "*"
    return f"[{entry['low']:>6.3f},{entry['high']:>6.3f}]{mark}"


def report_text(metrics: dict, config: dict, out) -> None:
    mode = metrics["agreement_type"]
    primary = f"ci_{thresholds.BOOTSTRAP_UNIT_PRIMARY}"
    secondary = f"ci_{thresholds.BOOTSTRAP_UNIT_SECONDARY}"
    alignment = config["alignment"]
    say = lambda text="": print(text, file=out)

    say(f"{EXPERIMENT} agreement -- {MODE_TITLES[mode]}")
    say(f"{alignment['n_items_compared']} items across "
        f"{alignment['n_conversations']} conversations")
    if alignment["items_excluded_unlabelled"]:
        say(f"excluded, unlabelled in at least one sheet: "
            f"{alignment['items_excluded_unlabelled']}")
    if alignment["items_only_in_sheet_a"] or alignment["items_only_in_sheet_b"]:
        say(f"not shared: {alignment['items_only_in_sheet_a']} only in sheet A, "
            f"{alignment['items_only_in_sheet_b']} only in sheet B")
    say()

    overall = metrics["overall"]
    say(f"Overall Cohen's kappa {_fmt(overall['kappa'])}   "
        f"{_fmt_ci(overall[primary])} by {thresholds.BOOTSTRAP_UNIT_PRIMARY}   "
        f"{_fmt_ci(overall[secondary])} by {thresholds.BOOTSTRAP_UNIT_SECONDARY}")
    say(f"Raw agreement         {_fmt(overall['percent_agreement'])}")
    if overall["kappa_undefined_reason"]:
        say(f"  kappa undefined: {overall['kappa_undefined_reason']}")
    say()

    say(f"Per category, one-vs-rest. Interval by {thresholds.BOOTSTRAP_UNIT_PRIMARY} "
        f"({int(thresholds.BOOTSTRAP_CI_LEVEL * 100)}%); * = not interpretable.")
    for label, entry in metrics["per_category"].items():
        flag = "" if entry["interpretable"] else "   <- not interpretable"
        say(f"  {label:<22} kappa {_fmt(entry['kappa'])}  {_fmt_ci(entry[primary])}  "
            f"n_either {entry['n_either']:>3}  (a {entry['n_rater_a']:>3} / "
            f"b {entry['n_rater_b']:>3} / both {entry['n_both']:>3}){flag}")
    for label, entry in metrics["per_category"].items():
        if entry["reason"]:
            say(f"  {label}: {entry['reason']}")
    say()

    value = metrics["value_agreement"]
    say(f"Value agreement over the {value['n_both_value']} items both sheets labelled VALUE")
    for normalization in thresholds.VALUE_NORMALIZATIONS:
        entry = value[normalization]
        tag = "primary" if normalization == value["primary_normalization"] else "secondary"
        say(f"  {normalization:<13} {_fmt(entry['agreement'])}  "
            f"{_fmt_ci(entry.get(primary))}  n {entry['n']:>3}  ({tag})")
    say()

    say("Confusion matrix, rows = sheet A, columns = sheet B")
    labels = metrics["confusion_matrix"]["labels"]
    say("  " + " " * 22 + "".join(f"{label[:6]:>8}" for label in labels))
    for label, row in zip(labels, metrics["confusion_matrix"]["counts"]):
        say(f"  {label:<22}" + "".join(f"{count:>8}" for count in row))
    say()

    decision = metrics["verdict"]
    say(f"Pre-registered threshold: kappa >= {decision['threshold']} per abstention type "
        f"({decision['threshold_source']})")
    for label, row in decision["per_abstention_type"].items():
        say(f"  {label:<22} kappa {_fmt(row['kappa'])}  n_either {row['n_either']:>3}  "
            f"{row['verdict']}")
    say()
    say(f"Hypothesis: {decision['hypothesis'].upper()} -- {decision['because']}")
    say(decision["note"])
    if mode == INTRA:
        say()
        say(INTRA_CONDITIONS)


def report_subsets(metrics: dict, out) -> None:
    """The per-subset blocks, each stating what its verdict may be read as.

    Printed after the combined report rather than instead of it, because the combined figure is
    what the sheets actually measured; the split is what makes it interpretable.
    """
    primary = f"ci_{thresholds.BOOTSTRAP_UNIT_PRIMARY}"
    print(file=out)
    print("=" * 72, file=out)
    print(f"BY SOURCE. Only the '{thresholds.ADR_003_SUBSET}' subset bears on ADR-003.", file=out)
    print("=" * 72, file=out)
    for name, block in metrics["by_source"].items():
        decision = block["verdict"]
        marker = "" if decision["bears_on_adr_003"] else "   <-- not evidence for ADR-003"
        print(file=out)
        print(f"[{name}] {block['n_items_compared']} items across "
              f"{block['n_conversations']} conversations{marker}", file=out)
        print(f"  reads as: {decision['reads_as']}", file=out)
        print(f"  overall kappa {_fmt(block['overall']['kappa'])}   "
              f"{_fmt_ci(block['overall'][primary])}   "
              f"raw agreement {_fmt(block['overall']['percent_agreement'])}", file=out)
        for label, row in decision["per_abstention_type"].items():
            print(f"    {label:<22} kappa {_fmt(row['kappa'])}  "
                  f"n_either {row['n_either']:>3}  {row['verdict']}", file=out)
        print(f"  hypothesis: {decision['hypothesis'].upper()} -- {decision['because']}",
              file=out)
    print(file=out)
    print("The synthetic conversations were written by a model that knows the taxonomy and "
          "wrote the", file=out)
    print("guideline, so agreement on them measures whether the guideline can be applied, not "
          "whether", file=out)
    print("the taxonomy survives real conversations. See experiments/EXP-000/synthetic/README.md.",
          file=out)


def main(argv=None, *, runs_root=None, scrubbed_root=None, out=sys.stdout) -> int:
    """`runs_root` and `scrubbed_root` are injected by tests so a test run can write to a

    temporary directory without loosening the containment checks the CLI enforces. The CLI
    never passes them, which is the same seam extract.py uses for data/raw/.
    """
    here = Path(__file__).parent
    parser = argparse.ArgumentParser(
        description="EXP-000 annotation agreement (run locally)",
        epilog="Exactly one of --sheets or --passes. The choice sets the agreement type, which "
               "is written into every output; there is no default and no --mode flag to get "
               "wrong.")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--sheets", nargs=2, metavar=("A", "B"), type=Path,
                        help="two annotators' sheets: inter-annotator agreement")
    source.add_argument("--passes", nargs=2, metavar=("FIRST", "SECOND"), type=Path,
                        help="one annotator's two passes: intra-annotator agreement")
    parser.add_argument("--out-root", type=Path, default=here / ".." / ".." / "runs" / EXPERIMENT,
                        help="runs/EXP-000; aggregates only")
    parser.add_argument("--disagreements-dir", type=Path,
                        default=here / ".." / ".." / "data" / "scrubbed" / EXPERIMENT,
                        help="must be inside data/scrubbed/")
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--seed", type=int, default=thresholds.BOOTSTRAP_SEED)
    parser.add_argument("--bootstrap", type=int, default=thresholds.BOOTSTRAP_RESAMPLES,
                        help="resamples per interval")
    parser.add_argument("--manifest", type=Path, default=None,
                        help="the sampler's manifest.json. With it, kappa is reported for the "
                             "real and synthetic subsets separately as well as combined; only "
                             "the real subset's verdict bears on ADR-003")
    parser.add_argument("--allow-partial-overlap", action="store_true",
                        help="measure on the shared items when the sheets differ, and record it")
    args = parser.parse_args(argv)

    mode = INTER if args.sheets else INTRA
    paths = tuple(args.sheets or args.passes)
    names = tuple(path.name for path in paths)

    sheet_a, sheet_b = (load_sheet(path) for path in paths)
    items, alignment = align(sheet_a, sheet_b, names=names,
                             allow_partial=args.allow_partial_overlap)

    run_id = args.run_id or (f"{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
                             f"-{git_output('rev-parse', 'HEAD')[:7]}")
    run_dir = safety.assert_in_runs(Path(args.out_root).expanduser().resolve() / run_id,
                                    EXPERIMENT, allowed_root=runs_root)
    disagreement_path = safety.assert_in_data_scrubbed(
        Path(args.disagreements_dir).expanduser().resolve() / f"disagreements_{run_id}.jsonl",
        allowed_root=scrubbed_root)

    sources = load_item_sources(args.manifest) if args.manifest else {}
    if sources:
        missing = [item["item_id"] for item in items if item["item_id"] not in sources]
        if missing:
            raise AgreementError(
                f"{len(missing)} labelled item(s) are absent from the manifest's item_source "
                f"map, e.g. {missing[0]}. The manifest and the sheets are from different "
                "sampler runs; pass the manifest written beside these sheets.")
        for item in items:
            item["source"] = sources[item["item_id"]]

    config = build_config(mode=mode, run_id=run_id, seed=args.seed, resamples=args.bootstrap,
                          sheet_paths=paths, report=alignment)
    metrics = {
        "experiment": EXPERIMENT,
        "agreement_type": mode,
        "run_id": run_id,
        **alignment,
        **measure(items, seed=args.seed, resamples=args.bootstrap),
    }
    metrics["verdict"] = verdict(metrics["per_category"],
                                 subset="combined" if sources else "combined")

    if sources:
        subsets = {}
        for name in sorted({item["source"] for item in items}):
            subset_items = [item for item in items if item["source"] == name]
            block = measure(subset_items, seed=args.seed, resamples=args.bootstrap)
            block["n_items_compared"] = len(subset_items)
            block["n_conversations"] = len({i["conversation_id"] for i in subset_items})
            block["verdict"] = verdict(block["per_category"], subset=name)
            subsets[name] = block
        metrics["by_source"] = subsets
        metrics["items_by_source"] = {
            name: block["n_items_compared"] for name, block in subsets.items()}
        metrics["adr_003_subset"] = thresholds.ADR_003_SUBSET

    metrics["notes"] = config["notes"]

    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    (run_dir / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    rows = disagreements(items)
    write_disagreements(disagreement_path, rows, mode=mode, run_id=run_id)

    report_text(metrics, config, out)
    if metrics.get("by_source"):
        report_subsets(metrics, out)
    print(file=out)
    print(f"aggregates: {run_dir}/metrics.json and config.json", file=out)
    print(f"{len(rows)} disagreement(s): {disagreement_path}", file=out)
    print("No item ids, labels or values are written under runs/.", file=out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
