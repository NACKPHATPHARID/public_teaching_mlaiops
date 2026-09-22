"""ITCS355 Lab 3 — load test (Locust alternative to k6).

    locust -f loadtest/locustfile.py --host https://<endpoint> \
           --users 10 --spawn-rate 5 --run-time 60s --headless

Batch vs single (Lab 3 TODO), run the comparison class on its own:

    TOKEN=$(gcloud auth print-identity-token) \
    locust -f loadtest/locustfile.py BatchVsSingleUser --host https://<endpoint> \
           --users 1 --spawn-rate 1 --run-time 60s --headless --only-summary

k6 (loadtest/k6.js) holds the latency target and the three concurrency levels; this file
holds the batch comparison, which needs per-round timing k6 does not give as easily.
"""
from __future__ import annotations

import os
import random
import time

from locust import HttpUser, between, task

BATCH_N = 50


def sample_payload() -> dict:
    return {
        "temp_c": round(random.uniform(60, 95), 3),
        "vibration_mm_s": round(random.uniform(1.0, 8.0), 3),
        "pressure_kpa": round(random.uniform(280, 350), 3),
        "hours_since_service": round(random.uniform(0, 9000), 3),
        "load_pct": round(random.uniform(20, 100), 3),
        "ambient_humidity": round(random.uniform(30, 85), 3),
    }


class _AuthUser(HttpUser):
    """The Cloud Run service is not public: send an identity token when one is given."""
    abstract = True

    def on_start(self):
        token = os.environ.get("TOKEN")
        if token:
            self.client.headers["Authorization"] = f"Bearer {token}"


class PredictUser(_AuthUser):
    wait_time = between(0.0, 0.1)

    @task(9)
    def predict(self):
        with self.client.post("/predict", json=sample_payload(), catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")

    @task(1)
    def predict_batch(self):
        rows = [sample_payload() for _ in range(BATCH_N)]
        with self.client.post("/predict/batch", json={"rows": rows}, catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")


class BatchVsSingleUser(_AuthUser):
    """Lab 3 TODO: the SAME 50 rows sent as 50 single calls, then as one batch call.
    Each round reports both totals as synthetic COMPARE entries, so Locust's stats table
    gives percentiles for each. Run at several --users levels to find where the batch
    advantage disappears."""
    wait_time = between(0.0, 0.1)

    @task
    def compare(self):
        rows = [sample_payload() for _ in range(BATCH_N)]
        ok = True

        t0 = time.perf_counter()
        for row in rows:
            r = self.client.post("/predict", json=row, name="/predict (inside 50-loop)")
            ok = ok and r.status_code == 200
        singles_ms = (time.perf_counter() - t0) * 1000

        t0 = time.perf_counter()
        r = self.client.post("/predict/batch", json={"rows": rows},
                             name=f"/predict/batch ({BATCH_N} rows)")
        ok = ok and r.status_code == 200
        batch_ms = (time.perf_counter() - t0) * 1000

        err = None if ok else RuntimeError("non-200 inside this round")
        for name, ms in ((f"{BATCH_N} singles, total", singles_ms),
                         (f"1 batch of {BATCH_N}, total", batch_ms)):
            self.environment.events.request.fire(
                request_type="COMPARE", name=name, response_time=ms,
                response_length=0, exception=err, context={})
