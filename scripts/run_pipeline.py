"""Lab 5: compile the pipeline for the active provider and submit it.

    python scripts/run_pipeline.py                      # gate reads the staging model from the registry
    python scripts/run_pipeline.py --incumbent 0.80     # demo override for the pass branch
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.pipelines import compile_for  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--incumbent", type=float, default=None)
    args = ap.parse_args()
    if args.incumbent is not None:
        os.environ["PIPELINE_INCUMBENT_ARG"] = f"--incumbent {args.incumbent}"
    compile_for(os.environ["CLOUD_PROVIDER"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
