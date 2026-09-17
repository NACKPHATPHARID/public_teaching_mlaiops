"""Training entry point.

Run locally:      python -m src.train --n-estimators 200 --max-depth 8
Run in Docker:    make reproduce
Run managed:      make train-remote        (Lab 2 — same image, on managed compute)

Every run logs: all hyperparameters, the seed, validation AND test metrics separately,
the data fingerprint, and the Git commit. A metric that cannot be traced to code and
data is not evidence of anything.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

import joblib
import mlflow
import mlflow.sklearn
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import average_precision_score, roc_auc_score

from src import config, data, seeds


def git_commit() -> str:
    # A managed job's container has no .git directory (the image never copies it), so the
    # submitter passes the commit the image was BUILT from as GIT_COMMIT. That env value
    # always wins over asking git directly.
    if os.environ.get("GIT_COMMIT"):
        return os.environ["GIT_COMMIT"]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True, cwd=config.REPO_ROOT,
        )
        return out.stdout.strip()
    except Exception:
        return "unknown"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="ITCS355 — reproducible training")
    p.add_argument("--n-estimators", type=int, default=200)
    p.add_argument("--max-depth", type=int, default=8)
    p.add_argument("--min-samples-leaf", type=int, default=5)
    p.add_argument("--seed", type=int, default=seeds.DEFAULT_SEED)
    p.add_argument("--experiment", default="itcs355-lab1")
    p.add_argument("--run-name", default=None)
    p.add_argument("--metrics-out", type=Path, default=None,
                   help="Write final metrics as JSON. Used by `make verify` and Lab 2 jobs.")
    p.add_argument("--model-out", type=Path, default=None,
                   help="Directory to write model.joblib into (Lab 2 managed trials).")
    p.add_argument("--no-track", action="store_true",
                   help="Skip MLflow entirely. Managed Lab 2 jobs run on ephemeral compute — "
                        "anything logged to the local sqlite tracking file here is destroyed "
                        "when the job ends, so tracking happens on the laptop instead, from "
                        "the metrics.json/model.joblib this writes.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cfg = config.load(strict=False)
    seed = seeds.set_all(args.seed)

    df = data.load_raw(cfg.raw_path)
    fingerprint = data.data_fingerprint(cfg.raw_path)
    train_df, val_df, test_df = data.split(df, seed=seed)

    model = RandomForestClassifier(
        n_estimators=args.n_estimators,
        max_depth=args.max_depth,
        min_samples_leaf=args.min_samples_leaf,
        random_state=seed,
        n_jobs=-1,
    )
    model.fit(train_df[data.FEATURES], train_df[data.TARGET])

    metrics: dict[str, float] = {}
    for name, part in (("val", val_df), ("test", test_df)):
        proba = model.predict_proba(part[data.FEATURES])[:, 1]
        metrics[f"{name}_roc_auc"] = float(roc_auc_score(part[data.TARGET], proba))
        metrics[f"{name}_pr_auc"] = float(average_precision_score(part[data.TARGET], proba))

    if not args.no_track:
        mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
        mlflow.set_experiment(args.experiment)
        with mlflow.start_run(run_name=args.run_name):
            mlflow.log_params({
                "n_estimators": args.n_estimators,
                "max_depth": args.max_depth,
                "min_samples_leaf": args.min_samples_leaf,
                "seed": seed,
                "n_features": len(data.FEATURES),
            })
            # Provenance. This is what makes the metric traceable.
            mlflow.set_tags({
                "git_commit": git_commit(),
                "data_fingerprint": fingerprint,
                "split_strategy": "group_by_machine_id",
                "n_train_rows": len(train_df),
                "n_val_rows": len(val_df),
                "n_test_rows": len(test_df),
            })
            mlflow.log_metrics(metrics)
            # MLflow 3 stores sklearn models with skops, which refuses types it hasn't been
            # told to trust. A plain RandomForest needs exactly this one — no custom classes.
            mlflow.sklearn.log_model(model, name="model",
                                     skops_trusted_types=["sklearn.tree._tree.Tree"])

    if args.model_out:
        # Plain joblib file, no custom classes — independent of wherever MLflow's own copy
        # lands, and what Task 5's reload_check.py ultimately needs reloadable.
        args.model_out.mkdir(parents=True, exist_ok=True)
        joblib.dump(model, args.model_out / "model.joblib")

    result = {"seed": seed, "data_fingerprint": fingerprint, "git_commit": git_commit(),
              **metrics}
    print(json.dumps(result, indent=2))
    if args.metrics_out:
        args.metrics_out.parent.mkdir(parents=True, exist_ok=True)
        args.metrics_out.write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
