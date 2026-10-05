"""Lab 4: scheduled drift check. Run by Cloud Scheduler through a Cloud Run job.

Reads the most recent feature log lines the service wrote, scores each feature against
the training reference, emits a metric per feature, and exits 2 when any feature is
over its own threshold.

Thresholds are per feature. See THRESHOLDS below and the Lab 4 section of the README.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from monitoring.drift import ks_statistic, psi
from src import config, data

WINDOW_ROWS = 3000
MIN_ROWS = 300  # below this, PSI on 10 bins is mostly noise, so do not alert

# 1.5 x the clean p99 PSI for 3000-row windows of whole machines (monitoring/calibrate.py),
# with a floor of 0.10. load_pct and temp_c need more headroom than the rest because a
# handful of machines can dominate a window, and machines differ a lot on those features.
THRESHOLDS = {
    "ambient_humidity": 0.10,
    "hours_since_service": 0.10,
    "load_pct": 0.25,
    "pressure_kpa": 0.10,
    "temp_c": 0.14,
    "vibration_mm_s": 0.10,
}


def recent_features(project: str, service: str, limit: int) -> pd.DataFrame:
    """Read the feature log lines through the Cloud Logging REST API (no gcloud needed)."""
    import urllib.request

    from cloudlayer.factory import get_adapter

    token = get_adapter(config.load(strict=False))._access_token()
    body = {
        "resourceNames": [f"projects/{project}"],
        "filter": ('resource.type="cloud_run_revision" '
                   f'AND resource.labels.service_name="{service}" '
                   'AND jsonPayload.event="features" '
                   'AND timestamp>=\"' + (pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ") + '\"'),
        "orderBy": "timestamp desc",
        "pageSize": min(limit, 1000),
    }
    rows: list[dict] = []
    while len(rows) < limit:
        req = urllib.request.Request(
            "https://logging.googleapis.com/v2/entries:list", method="POST",
            data=json.dumps(body).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            page = json.loads(resp.read())
        rows += [e["jsonPayload"] for e in page.get("entries", [])]
        if not page.get("nextPageToken"):
            break
        body["pageToken"] = page["nextPageToken"]
    return pd.DataFrame(rows[:limit])


def main() -> int:
    import os

    cfg = config.load(strict=False)
    service = os.environ.get("DRIFT_SERVICE", "itcs355-serve-staging")
    reference = pd.read_csv(Path(os.environ.get("DRIFT_REFERENCE", "data/raw/sensors.csv")))
    current = recent_features(cfg.project_id, service, WINDOW_ROWS)

    print(f"rows in window: {len(current)} (need {MIN_ROWS})")
    if len(current) < MIN_ROWS:
        print("not enough traffic to judge drift; no alert")
        return 0

    from cloudlayer.factory import get_adapter
    adapter = get_adapter(cfg)
    breached = []
    print(f"{'feature':<22}{'psi':>9}{'ks':>9}{'limit':>9}")
    for feature in data.FEATURES:
        ref = reference[feature].to_numpy(dtype=float)
        cur = current[feature].to_numpy(dtype=float)
        score, ks = psi(ref, cur), ks_statistic(ref, cur)
        limit = THRESHOLDS[feature]
        print(f"{feature:<22}{score:>9.4f}{ks:>9.4f}{limit:>9.2f}")
        adapter.emit_metric(f"drift.psi.{feature}", score)
        adapter.emit_metric(f"drift.ks.{feature}", ks)
        adapter.emit_metric(f"drift.limit.{feature}", limit)
        if score >= limit:
            breached.append(feature)
    adapter.emit_metric("drift.breached_features", float(len(breached)))
    adapter.emit_metric("drift.window_rows", float(len(current)))

    if breached:
        print("\nALERT: " + ", ".join(breached))
        print("Check the schema and the null rate before retraining. If the producer broke,"
              " fix it and do not retrain.")
        return 2
    print("\nOK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
