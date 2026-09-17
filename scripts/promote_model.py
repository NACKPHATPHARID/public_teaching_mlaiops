"""Lab 2, Task 4 — promote a registered version to `staging`, gated on evidence.

    make promote VERSION=<mlflow version>

The gate: all eight lineage fields present on the version, and reload_check passes against
it from the registry. Only then does the alias move — in MLflow and in Vertex.
"""
from __future__ import annotations

import argparse
import getpass
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mlflow
from mlflow.tracking import MlflowClient

from src import config

REQUIRED = ["git_commit", "data_version", "mlflow_run_id", "training_job_id",
            "image_digest", "seed", "metric_val", "metric_test"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True)
    ap.add_argument("--alias", default="staging")
    ap.add_argument("--skip-cloud", action="store_true")
    args = ap.parse_args()

    cfg = config.load(strict=False)
    mlflow.set_tracking_uri(cfg.mlflow_tracking_uri)
    client = MlflowClient()
    name = cfg.model_registry_name
    mv = client.get_model_version(name, args.version)

    missing = [k for k in REQUIRED if not mv.tags.get(k)]
    if missing:
        print(f"BLOCKED  version {args.version} is missing lineage: {missing}")
        return 1

    check = subprocess.run([sys.executable, "scripts/reload_check.py",
                            "--name", name, "--version", args.version])
    if check.returncode != 0:
        print(f"BLOCKED  reload_check failed for version {args.version}")
        return 1

    client.set_registered_model_alias(name, args.alias, args.version)
    client.set_model_version_tag(name, args.version, f"promoted_to_{args.alias}_by", getpass.getuser())
    client.set_model_version_tag(name, args.version, f"promoted_to_{args.alias}_at",
                                 datetime.now(timezone.utc).isoformat(timespec="seconds"))
    print(f"MLflow registry : {name} v{args.version} -> alias '{args.alias}'")

    cloud_v = mv.tags.get("cloud_registry_version")
    if cloud_v and not args.skip_cloud:
        from cloudlayer.factory import get_adapter
        get_adapter(cfg).set_model_alias(name, cloud_v, args.alias)
        print(f"Vertex registry : {name} v{cloud_v} -> alias '{args.alias}'")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
