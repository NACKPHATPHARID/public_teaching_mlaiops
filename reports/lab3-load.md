# Lab 3 - serving, load testing, rollback

Cloud Run service `itcs355-serve` in asia-southeast1, model from the Vertex registry.
Tested from my laptop in Bangkok, so all numbers include the round trip to Singapore.
Raw output in reports/lab3/.

## Target

p95 under 250 ms at 10 users, warm, errors under 1%. Committed to loadtest/k6.js in
660eb4f at 15:19 on 22 Sep; first results committed at 22:41 the same day. I picked it
because Bangkok to Singapore is 30-40 ms and a small tree model should score well under
50 ms, leaving room on top. Cold start is reported separately since Cloud Run scales to zero.

## Service

All four routes work. Bad input gets a 422 listing the missing fields, /health returns 200
while /ready still returns 503 until the model is loaded, every response carries
model_version, and the logs are JSON with request_id, latency_ms and model_version. Evidence
in task2-evidence.txt and task2-logs.txt.

No GCP code in app.py. deploy() resolves the Vertex version to a gs:// URI on my laptop and
passes it in as MODEL_ARTIFACT_URI; the container fetches it once at startup through the
adapter. Same idea as Vertex's own AIP_STORAGE_URI, and it meant I didn't have to add a
method to the seam. The Dockerfile only honours the injected $PORT, so the route differences
stay in the adapter (Cloud Run gets a startup probe on /ready, Vertex would get
--container-health-route instead).

Base image pinned to sha256:9534e5a8..., the same digest as the Lab 1 training image. The
3.11-slim tag had already moved to da047cb8... between the two labs, which is a decent
demonstration of why you pin. requirements-serve.txt is compiled with hashes under 3.11 to
match.

If /ready returned 200 too early, traffic would hit a container that can't score, so users
get 500s on every deploy and scale-out. I hit a version of this for real, below.

## Three concurrency levels

k6 in Docker, 60 s per run. No errors in any run in this lab.

Baseline (model as Lab 2 left it, 1 vCPU / 1 GiB, max 3, scale to zero):

| users | RPS  | p50   | p95   | p99   | max    |
|-------|------|-------|-------|-------|--------|
| 1     | 11.8 | 79.7  | 97.0  | 137.3 | 536 ms |
| 10    | 34.1 | 187.0 | 489.0 | 852.2 | 21.5 s |
| 50    | 78.1 | 504.0 | 1563  | 2648  | 3.66 s |

Missed at 10 users. It's queueing: 10/34 = 0.29 s and k6 measured 292 ms average. The 21.5 s
max is a scale-out cold start.

After the n_jobs fix (below), same hardware:

| users | RPS   | p50   | p95   | p99   | max    |
|-------|-------|-------|-------|-------|--------|
| 1     | 17.6  | 54.7  | 65.6  | 78.1  | 370 ms |
| 10    | 63.7  | 101.9 | 254.2 | 308.8 | 20.8 s |
| 50    | 167.0 | 191.3 | 900.3 | 1610  | 2.36 s |

Throughput doubled, p95 nearly halved, but still missed by 4 ms and the max was unchanged.
Scoring wasn't the problem any more, cold start was.

## Config that meets the target

1 vCPU / 1 GiB, n_jobs=1, --concurrency 4, 3 warm instances:

| users | RPS   | p50   | p95   | p99   | max    |
|-------|-------|-------|-------|-------|--------|
| 10    | 151.9 | 61.7  | 86.1  | 103.9 | 277 ms |
| 15    | 184.8 | 74.2  | 129.1 | 153.3 | 261 ms |
| 20    | 186.8 | 90.2  | 202.7 | 226.2 | 419 ms |
| 30    | 186.9 | 117.2 | 355.3 | 461.9 | 644 ms |

86 ms against a 250 ms target, and the tail is gone too.

The setting that fixed it was per-instance concurrency, not instance count. Cloud Run sends
up to 80 requests to one instance by default, which for a CPU-bound model stacks them behind
one busy vCPU: good median, bad tail. I tried min-instances 2 and 3 first at default
concurrency and both still failed (281 ms and 252 ms), which is what pointed me at the
distribution rather than capacity.

Breaking concurrency is between 20 and 30. Throughput flattens at about 185 RPS from 12 users
on, which is 3 instances times 4 slots full. After that more users just wait. Cloud Run queues
instead of rejecting so errors stayed at 0% even at 50 users. Not my client bottlenecking:
the same laptop pushed 167 and 187 RPS in these runs.

## Cold start

After about 50 minutes idle the first request took 16.63 s, the next two 0.129 s and 0.094 s.
So roughly 175x warm, which matches the 16-21 s maxima in the k6 runs. On a scale-to-zero
service this owns p99. (A sample after only 3 minutes idle gave 0.27 s, but that's TLS setup,
not a cold start. Noted as such in coldstart.txt.)

Most of the 16.6 s is booting, importing, and downloading the model. MLflow is still in the
image but unused at runtime; removing it would drop matplotlib, Flask and SQLAlchemy and
should cut this, but re-measuring needs another long idle window so I left it.

## Batch vs single

Locust, same 50 rows sent twice each round: 50 sequential /predict calls, then one
/predict/batch. Medians:

| users | batch of 50 | 50 singles | speed-up |
|-------|-------------|------------|----------|
| 1     | 57 ms       | 2800 ms    | 49x      |
| 5     | 76 ms       | 3900 ms    | 51x      |
| 10    | 65 ms       | 3400 ms    | 52x      |

About 1.1-1.5 ms per row batched against 56-78 ms singly. A single call is about 55 ms and
almost all of it is the round trip; scoring is about 8 ms. Fifty rows in one call still cost
about 57 ms because it's one round trip and sklearn scores them as one array. The batch saves
49 round trips.

The advantage didn't disappear in the range I tested, it grew. At 10 users the singles loop
triggered a scale-out and hit a cold start (p95 11 s) while batches stayed at 110 ms. It
would only shrink if I fired the 50 singles in parallel, which would finish in one round trip
but tie up 50 slots instead of 1.

## Payload size

/predict/batch at growing sizes over one connection. Above 100 rows the service returns 422,
but only after parsing the whole body, so those rows show serialization cost with no model
work.

| rows  | size    | status | p50    |
|-------|---------|--------|--------|
| 1     | 0.2 KB  | 200    | 55.2   |
| 50    | 7.3 KB  | 200    | 57.3   |
| 100   | 14.7 KB | 200    | 61.9   |
| 1000  | 147 KB  | 422    | 190.8  |
| 5000  | 733 KB  | 422    | 493.4  |
| 20000 | 2.9 MB  | 422    | 1331   |

Serialization takes over somewhere between 15 KB and 150 KB. Below 100 rows the fixed 55 ms
swamps everything (100x the data costs 7 ms). Above it each KB costs about 0.4 ms, so size
catches up with the fixed cost around 140 KB. The 1000-row request does no model work at all
and still takes 3x longer than scoring 100 rows. The 100-row schema cap keeps valid requests
in the cheap part. Some of the multi-MB time is my upload speed, not the server.

## Instance size

2 vCPU / 2 GiB: ceiling went from about 75 to about 115 RPS, p95 didn't improve, cost went
from $0.401 to $0.801/hour for three instances, so $0.00188 to $0.00234 per 1000, up 24%.
Double the price for 1.5x the throughput. Each prediction runs on one core, so more cores
mean more requests at once, not faster ones. Scale out, not up.

## Two things the load test found

A race between the uvicorn workers. Both workers load the model at startup and both wrote to
the same /tmp/model.joblib. On 1 vCPU they interleaved; on 2 vCPU they ran in parallel and one
read a half-written file (the empty "model load failed:" line on revision 00002-nxk). That
worker then had no model and answered every /predict with a 503 in about 3 ms. Two lessons:
the 2-CPU run "passed" its p95 precisely because 62% of requests were failing instantly and
dragging the percentile down, so latency has to be read with the error rate; and it's the
health versus readiness problem again, since readiness is per process but traffic is routed
per container. Fixed with one file per worker.

Thread overhead. The model was trained with n_jobs=-1, fine for fitting, but in serving it
means sklearn spins up and joins a thread pool for every single-row request. Measured locally:
35.9 ms per prediction as trained, 7.9 ms with n_jobs=1. So 78% of each request was thread
setup. Setting n_jobs=1 at load time is serving-only and the predictions are identical. make
smoke returned the same three probabilities before and after every change in this lab.

## Canary and rollback

Worse model: 30 trees at depth 2 instead of 100 at depth 4, registered as version 3. Val
ROC-AUC 0.8426 to 0.8332, test 0.8533 to 0.8442, so about 0.9 points worse.

Before running anything I scored both on the same 1200-row test split to pick the metric:

| metric              | v2     | v3     | requests @ 90/10 |
|---------------------|--------|--------|------------------|
| ROC-AUC             | 0.8533 | 0.8442 | impractical      |
| mean predicted p    | 0.1202 | 0.1211 | 11.7 M           |
| Brier               | 0.0803 | 0.0870 | 753 k            |
| share with p > 0.5  | 2.33%  | 0.00%  | about 19 k       |

The obvious metric is the wrong one. v3 never predicts above 0.5 because depth-2 trees can't
get that confident, so it quietly stops raising high-risk alerts while its average prediction
and AUC barely move. In production that's the dangerous failure, since machines that will fail
stop being flagged. Brier would have taken about 90 minutes at 90/10; the alert rate takes
minutes and needs no labels. I committed the rule to canary-rule.md before any canary traffic
ran. The detector only reads the probability from each response.

What happened (UTC):

- 16:00:26 baseline done, n=21342, r0 = 2.3662% (offline I predicted 2.33%)
- 16:01:04 split confirmed 90/10
- 16:03:40 alarm, alert rate 2.0736% below the 2.0805% threshold at n=25463, detection 156 s
- 16:04:18 rollback confirmed, 100% v2
- 16:04:25 onwards v3 serves nothing

30-second windows, counted from response bodies:

| window   | n    | v2   | v3  | v3 share | alert rate | errors |
|----------|------|------|-----|----------|------------|--------|
| 15:59:55 | 4665 | 4665 | 0   | 0.0%     | 2.49%      | 0      |
| 16:00:55 | 4846 | 4362 | 484 | 10.0%    | 1.77%      | 0      |
| 16:03:25 | 5000 | 4500 | 500 | 10.0%    | 2.24%      | 0      |
| 16:03:55 | 4646 | 4592 | 54  | 1.2%     | 2.45%      | 0      |
| 16:04:25 | 4745 | 4745 | 0   | 0.0%     | 2.07%      | 0      |
| 16:05:55 | 3690 | 3690 | 0   | 0.0%     | 2.11%      | 0      |

Traffic really moved: v3 at about 10% through the canary, 1.2% in the rollback window, then
zero. Zero errors throughout, which is the point, because the degradation was invisible in
availability.

The five lines:

1. The high-risk alert rate revealed it, share of responses with p above 0.5, no labels
   needed. It fell from 2.3662% baseline to 2.07% under the split.
2. Detection took 156 s after the split was confirmed, about 170 s after the first request
   actually reached v3, at 25463 requests.
3. Faster if I compared the two revisions' rates side by side instead of the blended rate,
   sent more traffic to the canary, or used a sequential test like CUSUM. Rechecking a
   3-sigma line every 5 s does inflate false-alarm risk.
4. At 50/50 the blended rate drops about 5x further, so detection would take about 760
   requests, call it 5 seconds. But half of all users lose their high-risk alerts while you
   wait, so 5x the blast radius for a 30x faster signal.
5. Rollback was one traffic change back to the model-v2 tag, confirmed in about 38 s, after
   which v3 served nothing. Honestly it was a narrow call: 2.074% against a 2.081% threshold,
   and the rate had hovered near the line since +95 s. That's probably what "worse by a small
   margin" should look like.

## Cost per 1000 predictions

Working in task5-cost.md. asia-southeast1 is Tier 2 so rates are 1.4x the Tier 1 list,
checked 23 Sep. 1 vCPU / 1 GiB = $0.1336 per instance-hour serving, $0.0252 idle.

  cost per 1000 = (instances * 3600 * [u*active + (1-u)*idle]) / (u * RPS * 3600) * 1000 + requests

with RPS = 151.9 measured:

| utilisation | $/hour | predictions/hour | $ per 1000 |
|-------------|--------|------------------|------------|
| 100%        | 0.4007 | 546,840          | 0.00113    |
| 30%         | 0.1731 | 164,052          | 0.00146    |
| 10%         | 0.1081 | 54,684           | 0.00238    |
| 1%          | 0.0789 | 5,468            | 0.01482    |

I'm assuming 30% average busy, and that's where the number is fragile: it moves 13x between
1% and 100%, because three warm instances bill at the idle rate whenever nobody calls. At low
traffic you're paying for readiness, not predictions. At min-instances 0 it's $0.00113
regardless of utilisation, but then every idle gap costs a 16.6 s cold start. About $54/month
of idle charges is the price of taking that out of p99.

Batch: three warm instances cost $54.43/month ($1.81/day) before serving anything, while a
nightly Cloud Run job at 1 vCPU / 1 GiB for a minute costs $0.0017 per run, $0.05/month, about
a thousand times less. Break-even is around 1.6 million predictions a day. At min-instances 0
the break-even disappears since there's no idle cost, and the decision becomes latency
(16.6 s cold start versus hours of delay) rather than money.

## Teardown

  $ make teardown LAB=3
  Deleting [itcs355-serve]...done.
  ['run-service:itcs355-serve']
  $ gcloud run services list --region asia-southeast1
  Listed 0 items.

I extended teardown() to delete Cloud Run services by the same lab=3 label it already used for
training jobs, and checked the console. Ran twice, once overnight partway through and once
after the final deploy and smoke test. Output in teardown.txt. Artifact Registry images and
the Vertex model versions are still there since they only cost storage and are needed for
grading.

## Evidence

reports/lab3/: task2-evidence.txt, task2-logs.txt, k6-c{1,10,50}, k6-tuned-*, k6-final-*,
k6-bp-*, k6-2cpu-*, k6-min3-*, coldstart.txt, batch-u{1,5,10}, payload.txt, canary-prep.txt,
canary-rule.md, canary-run.txt, canary-log.csv, canary-events.csv, task5-cost.md, teardown.txt.
