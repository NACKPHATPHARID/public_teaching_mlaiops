"""Lab 5 registration gate.

Compares a candidate against the incumbent model version in the registry and exits
non-zero when the candidate should NOT be registered. That exit code is what makes the
pipeline condition real.

    python scripts/evaluation_gate.py --metrics reports/metrics.json
    python scripts/evaluation_gate.py --metrics reports/metrics.json --incumbent 0.90
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Margins come from my own Lab 2 seed study: test_roc_auc had a std of 0.0146 across
# 5 seeds. MIN_IMPROVEMENT is about one std, so a gain smaller than what a different
# random seed gives is treated as noise. MIN_ABSOLUTE is about 3.7 std below the mean
# of 0.854, so a score under it means the run is broken, not unlucky.
MIN_ABSOLUTE = 0.80
MIN_IMPROVEMENT = 0.015


def read_incumbent(alias: str) -> float | None:
    from cloudlayer.factory import get_adapter
    from src import config

    cfg = config.load(strict=False)
    return get_adapter(cfg).get_model_metric(cfg.model_registry_name, alias)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--metrics", type=Path, required=True)
    ap.add_argument("--metric", default="test_roc_auc")
    ap.add_argument("--incumbent", type=float, default=None,
                    help="incumbent score; omit to read it from the registry")
    ap.add_argument("--incumbent-alias", default="staging",
                    help="registry alias that marks the incumbent version")
    ap.add_argument("--decision-out", type=Path, default=None,
                    help="write 'pass' or 'fail' here for the pipeline condition")
    args = ap.parse_args()

    def finish(ok: bool, message: str) -> int:
        print(message)
        if args.decision_out:
            args.decision_out.parent.mkdir(parents=True, exist_ok=True)
            args.decision_out.write_text("pass" if ok else "fail")
        return 0 if ok else 1

    payload = json.loads(args.metrics.read_text())
    candidate = float(payload[args.metric])
    print(f"candidate {args.metric} = {candidate:.4f}")

    if candidate < MIN_ABSOLUTE:
        return finish(False, f"GATE FAIL  below absolute floor {MIN_ABSOLUTE}")

    incumbent = args.incumbent
    if incumbent is None:
        try:
            incumbent = read_incumbent(args.incumbent_alias)
        except Exception as e:  # fail closed: no registry answer means no registration
            return finish(False, f"GATE FAIL  could not read the registry: {e}")
        if incumbent is None:
            return finish(True, f"no version has alias '{args.incumbent_alias}', "
                                "treating as first registration\nGATE PASS")

    delta = candidate - incumbent
    print(f"incumbent {incumbent:.4f}  delta {delta:+.4f}  required {MIN_IMPROVEMENT:+.4f}")
    if delta < MIN_IMPROVEMENT:
        return finish(False, "GATE FAIL  improvement within noise; not registering")
    return finish(True, "GATE PASS")


if __name__ == "__main__":
    raise SystemExit(main())
