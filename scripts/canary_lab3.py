"""Lab 3 Task 4: 90/10 canary, metric-only detection, automatic rollback.

The detector reads ONLY the probability in each response (high-risk alert rate, p > 0.5),
as stated in reports/lab3/canary-rule.md before this ran. model_version is logged for the
evidence table afterwards and is never read by the detector.

    URL=https://... python scripts/canary_lab3.py | tee reports/lab3/canary-run.txt
"""
import csv
import http.client
import json
import math
import os
import random
import subprocess
import sys
import threading
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloudlayer.factory import get_adapter  # noqa: E402
from src import config, data, seeds  # noqa: E402

SERVICE, PROD, CANARY = "itcs355-serve", "model-v2", "model-v3"
WORKERS, BASELINE_S, SKIP_S, MAX_CANARY_S, AFTER_S = 10, 180, 30, 900, 120
MIN_N, CHECK_S = 2000, 5
OUT = Path("reports/lab3")

cfg = config.load()
adapter = get_adapter(cfg)
seed = seeds.set_all(seeds.DEFAULT_SEED)
_, _, test_df = data.split(data.load_raw(cfg.raw_path), seed=seed)
ROWS = json.loads(test_df[data.FEATURES].to_json(orient="records"))

u = urllib.parse.urlparse(os.environ["URL"])
TOKEN = subprocess.run(["gcloud", "auth", "print-identity-token"],
                       capture_output=True, text=True, check=True).stdout.strip()
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

log, lock, stop, events = [], threading.Lock(), threading.Event(), []


def iso(t):
    return datetime.fromtimestamp(t, timezone.utc).isoformat(timespec="seconds")


def mark(name, extra=""):
    t = time.time()
    events.append((iso(t), name, extra))
    print(f"[{iso(t)}] {name} {extra}", flush=True)
    return t


def worker():
    conn = http.client.HTTPSConnection(u.netloc, timeout=60)
    while not stop.is_set():
        body = json.dumps(random.choice(ROWS)).encode()
        try:
            conn.request("POST", "/predict", body=body, headers=HEADERS)
            r = conn.getresponse()
            raw = r.read()
        except (http.client.HTTPException, OSError):
            conn.close()
            conn = http.client.HTTPSConnection(u.netloc, timeout=60)
            continue
        t = time.time()
        if r.status == 200:
            d = json.loads(raw)
            rec = (t, float(d["probability"]), str(d.get("model_version")), 200)
        else:
            rec = (t, None, None, r.status)
        with lock:
            log.append(rec)


def alert_rate(since):
    """Detector input: probabilities only."""
    with lock:
        ps = [p for t, p, _v, _s in log if t >= since and p is not None]
    return len(ps), (sum(p > 0.5 for p in ps) / len(ps) if ps else 0.0)


print(adapter.set_traffic(SERVICE, {PROD: 100}))
threads = [threading.Thread(target=worker, daemon=True) for _ in range(WORKERS)]
for th in threads:
    th.start()
t0 = mark("baseline start", "100% model-v2")
time.sleep(BASELINE_S)
n0, r0 = alert_rate(t0 + SKIP_S)
mark("baseline done", f"n={n0} r0={r0:.4%}")

split_yaml = adapter.set_traffic(SERVICE, {PROD: 90, CANARY: 10})
t_split = mark("SPLIT 90/10", "")
print(split_yaml, flush=True)

alarm = None
while time.time() - t_split < MAX_CANARY_S:
    time.sleep(CHECK_S)
    n, r = alert_rate(t_split)
    thr = r0 - 3 * math.sqrt(r0 * (1 - r0) / n) if n else 0.0
    print(f"  +{time.time() - t_split:4.0f}s  n={n:6d}  alert_rate={r:.4%}  alarm_below={thr:.4%}",
          flush=True)
    if n >= MIN_N and r < thr:
        alarm = mark("ALARM", f"n={n} alert_rate={r:.4%} threshold={thr:.4%} "
                              f"detection_s={time.time() - t_split:.0f}")
        break
if alarm is None:
    mark("NO ALARM within max canary window", f"{MAX_CANARY_S}s")

rb_yaml = adapter.set_traffic(SERVICE, {PROD: 100})
mark("ROLLBACK done", "100% model-v2")
print(rb_yaml, flush=True)
time.sleep(AFTER_S)
stop.set()
for th in threads:
    th.join(timeout=70)
mark("traffic stopped")

with open(OUT / "canary-log.csv", "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["utc", "probability", "model_version", "status"])
    for t, p, v, s in log:
        w.writerow([iso(t), p, v, s])
with open(OUT / "canary-events.csv", "w", newline="") as f:
    csv.writer(f).writerows([("utc", "event", "detail"), *events])

print("\nEvidence: 30-second windows (model_version used here only, after the fact)")
print(f"{'window start (UTC)':22s} {'n':>6s} {'v2':>6s} {'v3':>6s} {'v3 share':>9s} "
      f"{'alert rate':>11s} {'errors':>7s}")
start = min(t for t, *_ in log)
buckets = {}
for t, p, v, s in log:
    b = buckets.setdefault(int((t - start) // 30), [0, 0, 0, 0, 0])
    b[0] += 1
    b[1] += v == "2"
    b[2] += v == "3"
    b[3] += p is not None and p > 0.5
    b[4] += s != 200
for k in sorted(buckets):
    n, v2, v3, al, er = buckets[k]
    ok = max(v2 + v3, 1)
    print(f"{iso(start + 30 * k):22s} {n:6d} {v2:6d} {v3:6d} {v3 / ok:9.1%} "
          f"{al / ok:11.2%} {er:7d}")
