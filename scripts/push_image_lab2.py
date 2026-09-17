"""Push the image built by `make image` and record which commit it came from.

    make image-lab2

Writes reports/lab2-image.json. src/tune.py refuses to run if HEAD differs from the commit
recorded here, because a run logged against the wrong image breaks the lineage chain
(image_digest -> git_commit) that Task 4 grades.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from cloudlayer.factory import get_adapter
from src import config
from src.train import git_commit


def main() -> int:
    local_tag = sys.argv[1]
    dirty = subprocess.run(
        ["git", "status", "--porcelain", "src", "cloudlayer", "Dockerfile",
         "requirements.txt", ".dvc", "data/raw.dvc"],
        capture_output=True, text=True).stdout.strip()
    if dirty:
        print("Commit your changes first — this image would not match any commit:\n" + dirty)
        return 1
    ref = get_adapter(config.load()).push_image(local_tag)
    out = Path("reports/lab2-image.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"image_uri": ref, "git_commit": git_commit(),
                               "local_tag": local_tag}, indent=2))
    print(f"wrote {out}\n  image_uri  {ref}\n  git_commit {git_commit()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
