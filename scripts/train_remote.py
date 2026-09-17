"""Lab 2, Task 1 — run the Lab 1 training container once, as a managed job.

    make train-remote

Reads data via `dvc pull` (from the DVC remote under BLOB_URI), writes metrics.json and
model.joblib back under BLOB_URI, and depends on nothing on your laptop except this script
submitting it. Expect a permissions error the first time — write down exactly what it says,
Drill 2 asks.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config
from src.train import git_commit


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--image-file", type=Path, default=Path("reports/lab2-image.json"))
    ap.add_argument("--instance", default="n1-standard-4")
    ap.add_argument("--spot", action=argparse.BooleanOptionalAction, default=True)
    args = ap.parse_args()

    cfg = config.load()
    adapter = get_adapter(cfg)
    if not args.image_file.exists():
        sys.exit(f"{args.image_file} missing. Run `make image-lab2` first.")
    image = json.loads(args.image_file.read_text())

    job_id = adapter.submit_training(image["image_uri"], {
        "module": "src.train",
        "hyperparams": {"n_estimators": 200, "max_depth": 8, "min_samples_leaf": 5,
                        "no_track": True},
        "output_key": "lab2/train-remote",
        "instance": args.instance,
        "spot": args.spot,
        "labels": {"study": "train-remote"},
        "env": {"GIT_COMMIT": git_commit()},
        "display_name": "itcs355-lab2-train-remote",
    })
    print(f"submitted job_id={job_id}")
    result = adapter.wait_training(job_id)
    print(json.dumps(result, indent=2))
    if not result["succeeded"]:
        print(f"logs: {result.get('console_url', '')}")
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        adapter.download_key("lab2/train-remote/metrics.json", f"{tmp}/metrics.json")
        metrics = json.loads(Path(f"{tmp}/metrics.json").read_text())
    print(f"\nPASS  managed job wrote back val_roc_auc={metrics['val_roc_auc']:.4f} "
          f"test_roc_auc={metrics['test_roc_auc']:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
