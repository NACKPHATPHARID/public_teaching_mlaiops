"""Lab 2 — prove the registered model can be reloaded by version, from the registry.

    python scripts/reload_check.py --name itcs355-<studentid> --version 3
    python scripts/reload_check.py --name itcs355-<studentid> --alias staging

This is the lab's quiet test. Models that cannot be reloaded six months later are the
commonest form of dead work in industry, and the cause is nearly always a serialization
assumption: a custom class that no longer exists, a library version that moved, a
preprocessing step that only ever lived in a notebook.

Loading from a local file instead of the registry defeats the purpose and is checked.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
from mlflow.tracking import MlflowClient

from src import config, data, seeds

LINEAGE = ["git_commit", "data_version", "mlflow_run_id", "training_job_id",
          "image_digest", "seed", "metric_val", "metric_test"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True, help="registered model name")
    ap.add_argument("--version", default=None)
    ap.add_argument("--alias", default=None)
    ap.add_argument("--rows", type=int, default=5)
    args = ap.parse_args()
    if not (args.version or args.alias):
        ap.error("give --version or --alias")

    cfg = config.load(strict=False)
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    client = MlflowClient()

    mv = (client.get_model_version(args.name, args.version) if args.version
          else client.get_model_version_by_alias(args.name, args.alias))
    uri = f"models:/{args.name}/{mv.version}"
    print(f"loading {uri}  (registry: {cfg.mlflow_tracking_uri})")

    missing = [k for k in LINEAGE if not mv.tags.get(k)]
    for k in LINEAGE:
        print(f"  {k:<16} {mv.tags.get(k, '-- MISSING --')}")
    if missing:
        print(f"FAIL  lineage missing on the registered version: {missing}")
        return 1

    model = mlflow.sklearn.load_model(uri)

    df = data.load_raw(cfg.raw_path)
    _, _, test_df = data.split(df, seed=seeds.DEFAULT_SEED)
    sample = test_df.head(args.rows)
    preds = model.predict_proba(sample[data.FEATURES])[:, 1]

    for rid, p in zip(sample[data.ID], preds):
        print(f"  reading {rid}: p(failure)={p:.4f}")
    print("\nPASS  model reloaded from the registry and scored rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
