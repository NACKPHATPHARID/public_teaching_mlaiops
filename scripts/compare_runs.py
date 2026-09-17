"""Lab 2 — rank tracked runs by metric AND by cost per point.

    python scripts/compare_runs.py --experiment itcs355-lab2

Writes reports/lab2-comparison.md. Builds its own markdown table instead of calling
DataFrame.to_markdown(), which needs the `tabulate` package — not in requirements.txt, so
the original version of this script would crash the first time you ran it.

The cost-per-point column is what the lab is about: the highest-scoring run is frequently
not the one you should register. Your 200-word justification lives in
reports/lab2-justification.md and is pasted in here on every run, so re-running this script
never wipes what you wrote.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
import pandas as pd

from src import config

JUSTIFICATION = Path("reports/lab2-justification.md")
PRICING = Path("reports/lab2-pricing.md")
HYPER = ["n_estimators", "max_depth", "min_samples_leaf"]


def md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    rows = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    for _, r in df.iterrows():
        rows.append("| " + " | ".join("" if pd.isna(r[c]) else str(r[c]) for c in cols) + " |")
    return "\n".join(rows)


def col(runs: pd.DataFrame, name: str):
    return runs[name] if name in runs.columns else pd.Series([None] * len(runs), index=runs.index)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default="itcs355-lab2")
    ap.add_argument("--metric", default="val_roc_auc")
    ap.add_argument("--out", type=Path, default=Path("reports/lab2-comparison.md"))
    args = ap.parse_args()

    cfg = config.load(strict=False)
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    exp = mlflow.get_experiment_by_name(args.experiment)
    if exp is None:
        print(f"No experiment named {args.experiment!r}. Run `make tune` first.")
        return 1
    runs = mlflow.search_runs(experiment_ids=[exp.experiment_id])
    if runs.empty:
        print("No runs found.")
        return 1

    m = f"metrics.{args.metric}"
    table = pd.DataFrame({
        "run_id": runs["run_id"].str[:8],
        "study": col(runs, "tags.study"),
        **{h: col(runs, f"params.{h}") for h in HYPER},
        "seed": col(runs, "params.seed"),
        args.metric: runs[m].round(4),
        "test_roc_auc": col(runs, "metrics.test_roc_auc").round(4),
        "billed_s": col(runs, "metrics.duration_s").round(0),
        "cost_thb": col(runs, "metrics.cost_thb").fillna(0).round(4),
        "instance": col(runs, "params.instance"),
        "job_id": col(runs, "tags.training_job_id"),
    })
    baseline = table[args.metric].min()
    gain = (table[args.metric] - baseline).clip(lower=1e-9)
    table["thb_per_point"] = (table["cost_thb"] / (gain * 100)).round(2)
    table.loc[gain <= 1e-9, "thb_per_point"] = None
    table = table.sort_values(args.metric, ascending=False)

    grid_runs = table[table["study"] == "grid"]
    spread = (grid_runs[args.metric].max() - grid_runs[args.metric].min()) if len(grid_runs) else float("nan")

    lines = [
        "# Lab 2 — Run comparison", "",
        f"Experiment `{args.experiment}` · {len(table)} runs · "
        f"total estimated spend **{table['cost_thb'].sum():.2f} THB** of 150 THB · "
        f"instances: {', '.join(sorted(map(str, table['instance'].dropna().unique())))}", "",
        "`thb_per_point` = cost per percentage point of "
        f"{args.metric} above the worst trial. Cheap improvements rank low; expensive "
        "improvements rank high, however good the headline number is.", "",
        "## Hyperparameter study", "",
        md_table(grid_runs.drop(columns=["study"])) if len(grid_runs) else "_no grid runs yet_", "",
        f"Spread across the study (best − worst {args.metric}): **{spread:.4f}**", "",
    ]

    seed_runs = table[table["study"] == "seed-variance"]
    if len(seed_runs) >= 2:
        vals, tvals = seed_runs[args.metric], seed_runs["test_roc_auc"]
        sd = vals.std(ddof=1)
        cfg_desc = ", ".join(f"{h}={seed_runs.iloc[0][h]}" for h in HYPER)
        lines += ["## Seed variance for the chosen configuration", "",
                  f"Configuration: `{cfg_desc}` · {len(seed_runs)} seeds", "",
                  md_table(seed_runs[["run_id", "seed", args.metric, "test_roc_auc", "cost_thb"]]),
                  "",
                  f"- {args.metric}: mean **{vals.mean():.4f}**, std **{sd:.4f}**, "
                  f"range {vals.min():.4f}–{vals.max():.4f}",
                  f"- test_roc_auc: mean **{tvals.mean():.4f}**, std **{tvals.std(ddof=1):.4f}**"]
        if len(grid_runs):
            best = grid_runs[args.metric].max()
            close = int((grid_runs[args.metric] >= best - 2 * sd).sum())
            lines += [f"- {close} of {len(grid_runs)} study configurations are within 2 std "
                      f"({2 * sd:.4f}) of the best — those cannot be ranked apart by this evidence"]
        lines += [""]

    lines += ["## Pricing check", ""]
    lines += [PRICING.read_text().strip() if PRICING.exists() else
              "TODO(Lab 2): write reports/lab2-pricing.md — date checked, pricing page URL, the "
              "rate for your instance in your region, and whether it matched src/costs.py."]
    lines += ["", "## Which model did you register, and why?", ""]
    if JUSTIFICATION.exists():
        lines += [JUSTIFICATION.read_text().strip()]
    else:
        lines += [
            "TODO(Lab 2): write reports/lab2-justification.md (200 words maximum), then re-run.",
            "Must address all four:", "",
            "1. Why this model rather than the highest-scoring one, if they differ",
            "2. The variance across seeds for your chosen configuration",
            "3. What it costs to train, and to retrain monthly",
            "4. One way this choice could be wrong",
        ]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")
    print(f"wrote {args.out}  ({len(table)} runs)")
    print(table.head(8).to_string(index=False))
    if JUSTIFICATION.exists():
        n = len(JUSTIFICATION.read_text().split())
        print(f"\njustification: {n} words" + ("  <-- OVER 200" if n > 200 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
