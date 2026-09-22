"""Lab 3 Task 3: payload size vs latency on /predict/batch.

Above the 100-row schema limit the service answers 422, but only after receiving and
parsing the whole body, so those rows isolate transfer + JSON parsing + validation cost.
One persistent HTTPS connection, so TLS setup is not counted.

    URL=... TOKEN=$(gcloud auth print-identity-token) python scripts/payload_lab3.py
"""
import http.client
import json
import os
import random
import statistics
import time
import urllib.parse

u = urllib.parse.urlparse(os.environ["URL"])
HEADERS = {"Authorization": f"Bearer {os.environ['TOKEN']}", "Content-Type": "application/json"}
conn = http.client.HTTPSConnection(u.netloc, timeout=120)


def row():
    return {"temp_c": round(random.uniform(60, 95), 3),
            "vibration_mm_s": round(random.uniform(1, 8), 3),
            "pressure_kpa": round(random.uniform(280, 350), 3),
            "hours_since_service": round(random.uniform(0, 9000), 3),
            "load_pct": round(random.uniform(20, 100), 3),
            "ambient_humidity": round(random.uniform(30, 85), 3)}


def call(body):
    global conn
    for attempt in range(2):
        try:
            t = time.perf_counter()
            conn.request("POST", "/predict/batch", body=body, headers=HEADERS)
            r = conn.getresponse()
            r.read()
            return (time.perf_counter() - t) * 1000, r.status
        except (http.client.HTTPException, ConnectionError, OSError):
            conn.close()
            conn = http.client.HTTPSConnection(u.netloc, timeout=120)
    raise RuntimeError("request failed twice")


print(f"{'rows':>7} {'KB':>9} {'status':>6} {'p50 ms':>9} {'p95 ms':>9} {'ms per KB':>10}")
for n in [1, 10, 25, 50, 100, 1000, 5000, 20000]:
    body = json.dumps({"rows": [row() for _ in range(n)]}).encode()
    call(body)  # warm-up, not counted
    reps = 20 if n <= 1000 else 6
    results = [call(body) for _ in range(reps)]
    times = sorted(ms for ms, _ in results)
    status = results[-1][1]
    p50 = statistics.median(times)
    p95 = times[max(0, round(0.95 * len(times)) - 1)]
    kb = len(body) / 1024
    print(f"{n:>7} {kb:>9.1f} {status:>6} {p50:>9.1f} {p95:>9.1f} {p50 / kb:>10.2f}")
