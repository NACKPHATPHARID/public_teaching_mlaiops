"""Lab 5 pipeline step: register the trained model as a new Vertex version.

Only runs when the gate said pass (the pipeline condition guards it). The score goes
into the version description as metric_test=..., which the next gate reads as incumbent.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter  # noqa: E402
from src import config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True, help="folder train wrote to, e.g. /gcs/bucket/lab5/run1")
    ap.add_argument("--run-id", default="local")
    ap.add_argument("--version-out", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    run = Path(args.run_dir)
    result = json.loads((run / "metrics.json").read_text())
    model_uri = "gs://" + str(run / "model").removeprefix("/gcs/")

    lineage = {
        "git_commit": result.get("git_commit", "unknown"),
        "data_version": result.get("data_fingerprint", "unknown"),
        "seed": result.get("seed", "unknown"),
        "metric_val": result["val_roc_auc"],
        "metric_test": result["test_roc_auc"],
        "pipeline_run": args.run_id,
    }
    if args.dry_run:
        print("would register", model_uri)
        print(json.dumps(lineage, indent=2))
        return 0

    cfg = config.load()
    version = get_adapter(cfg).register_model(
        model_uri, cfg.model_registry_name, labels=lineage, aliases=["candidate"])
    print(f"registered {cfg.model_registry_name} version {version} (alias candidate)")
    if args.version_out:
        args.version_out.parent.mkdir(parents=True, exist_ok=True)
        args.version_out.write_text(version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
