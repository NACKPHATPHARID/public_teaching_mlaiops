"""Lab 2, Task 4 — register the chosen run with lineage on the VERSION, in both registries.

    make register RUN_ID=<8-char or full mlflow run id>

Two registries, one version of the truth:
  * MLflow Model Registry  — portable, what reload_check.py and Lab 3 load from
  * Vertex Model Registry  — the cloud-native one Task 4's "Provider notes" ask for

Both get the same 8 lineage fields and the alias `candidate`. `make promote` moves a
version to `staging` later, gated on lineage completeness and a passing reload check.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
from mlflow.tracking import MlflowClient

from cloudlayer.factory import get_adapter
from src import config

REQUIRED = ["git_commit", "data_version", "mlflow_run_id", "training_job_id",
            "image_digest", "seed", "metric_val", "metric_test"]


def find_run(client: MlflowClient, experiment: str, run_id: str):
    if len(run_id) == 32:
        return client.get_run(run_id)
    exp = client.get_experiment_by_name(experiment)
    matches = [r for r in client.search_runs([exp.experiment_id], max_results=5000)
              if r.info.run_id.startswith(run_id)]
    if len(matches) != 1:
        sys.exit(f"run id prefix {run_id!r} matched {len(matches)} runs — use more characters")
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True, help="mlflow run_id (or an 8-char prefix) of the chosen trial")
    ap.add_argument("--experiment", default="itcs355-lab2")
    ap.add_argument("--skip-cloud", action="store_true", help="MLflow registry only (debug)")
    args = ap.parse_args()

    cfg = config.load(strict=False)
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    client = MlflowClient()
    run = find_run(client, args.experiment, args.run_id)
    tags, params, metrics = run.data.tags, run.data.params, run.data.metrics

    lineage = {
        "git_commit": tags.get("git_commit", ""),
        "data_version": tags.get("data_version", ""),
        "mlflow_run_id": run.info.run_id,
        "training_job_id": tags.get("training_job_id", ""),
        "image_digest": tags.get("image_digest", ""),
        "seed": params.get("seed", ""),
        "metric_val": f"{metrics.get('val_roc_auc', 0):.4f}",
        "metric_test": f"{metrics.get('test_roc_auc', 0):.4f}",
    }
    bad = [k for k in REQUIRED if lineage.get(k) in ("", None, "unknown", "local")]
    if bad:
        sys.exit(f"Refusing to register: lineage fields missing or not real: {bad}\n"
                 "A trial run locally or from a dirty tree cannot be traced. Pick a run from "
                 "`make tune` (a real managed job) on a committed tree.")

    name = cfg.model_registry_name

    # 1) MLflow registry. Tags go on the model VERSION — tags on the run alone are half credit.
    mv = mlflow.register_model(f"runs:/{run.info.run_id}/model", name)
    for k, v in lineage.items():
        client.set_model_version_tag(name, mv.version, k, str(v))
    client.set_registered_model_alias(name, "candidate", mv.version)
    print(f"MLflow registry : {name} version {mv.version}  (alias: candidate)")

    # 2) Vertex Model Registry, same lineage, pointing at the plain model.joblib the managed
    # job itself wrote to GCS (not MLflow's own copy, which only ever exists on your laptop).
    if not args.skip_cloud:
        output_key = tags.get("output_key")
        if not output_key:
            sys.exit("run has no 'output_key' tag — was it produced by this version of src/tune.py?")
        cloud_model_uri = f"{cfg.blob_uri.rstrip('/')}/{output_key}/model"
        cloud_version = get_adapter(cfg).register_model(
            cloud_model_uri, name, labels=lineage, aliases=["candidate"])
        client.set_model_version_tag(name, mv.version, "cloud_registry_version", cloud_version)
        print(f"Vertex registry : {name} version {cloud_version}  (alias: candidate)")

    print("\nlineage on this version:")
    for k in REQUIRED:
        print(f"  {k:<16} {lineage[k]}")
    print(f"\nnext:  make reload-check VERSION={mv.version}   then   make promote VERSION={mv.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
