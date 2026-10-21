"""Lab 5 pipeline step: deploy the registered version to staging, then move the alias.

The alias moves only after the deploy succeeded, so `staging` never points at a
version that failed to start.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter  # noqa: E402
from src import config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version-file", type=Path, required=True)
    ap.add_argument("--service", default="itcs355-lab5-staging")
    ap.add_argument("--instance", default="1/1Gi")
    ap.add_argument("--alias", default="staging")
    args = ap.parse_args()

    version = args.version_file.read_text().strip()
    cfg = config.load()
    adapter = get_adapter(cfg)
    url = adapter.deploy(version, args.service, args.instance)
    adapter.set_model_alias(cfg.model_registry_name, version, args.alias)
    print(f"deployed version {version} to {url}; alias {args.alias} moved")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
