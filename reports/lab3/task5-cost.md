# Lab 3 Task 5 — cost per 1,000 predictions

Rates: Cloud Run services, request-based billing, asia-southeast1 = **Tier 2** (1.4x Tier 1 list),
verified against https://cloud.google.com/run/pricing on 2026-09-23.

| Item | Tier 1 list | Tier 2 (used here) |
|---|---|---|
| CPU active | $0.000024 /vCPU-s | $0.0000336 |
| Memory active | $0.0000025 /GiB-s | $0.0000035 |
| CPU + memory idle (min-instances) | $0.0000025 each | $0.0000035 each |
| Requests | $0.40 /million | $0.40 /million |

1 vCPU / 1 GiB => $0.1336 per instance-hour serving, $0.0252 per instance-hour warm-idle.

## Method

cost per 1,000 = (instances * 3600 * [u*active + (1-u)*idle]) / (u * RPS * 3600) * 1000 + request fee

Measured RPS = 151.9 at 10 VUs on the config that meets the p95 target
(1 vCPU, n_jobs=1, --concurrency 4, 3 warm instances; p95 86 ms).

## Utilisation assumption (stated: 30% average busy)

| util | $/hour | preds/hour | $ per 1,000 |
|---|---|---|---|
| 100% | 0.4007 | 546,840 | 0.00113 |
| 80%  | 0.3357 | 437,472 | 0.00117 |
| 30%  | 0.1731 | 164,052 | **0.00146** |
| 10%  | 0.1081 |  54,684 | 0.00238 |
| 1%   | 0.0789 |   5,468 | 0.01482 |

The figure moves 13x between 1% and 100%: the three warm instances bill at the idle
rate whenever nobody calls, so at low traffic you pay for readiness, not predictions.

At min-instances 0: $0.00113 per 1,000, independent of utilisation — but each idle gap
costs a 16.6 s cold start. ~$54/month of idle charges is the price of removing that.

## Instance size (cost side of the Task 3 finding)

| Config | ceiling | $/hour (3 busy) | $ per 1,000 |
|---|---|---|---|
| 1 vCPU / 1 GiB | ~75 RPS | 0.401 | 0.00188 |
| 2 vCPU / 2 GiB | ~115 RPS | 0.801 | 0.00234 |

2x the price for 1.5x the throughput: +24% per prediction, no latency gain.
Scale out, not up.

## Batch vs warm endpoint

Three warm instances: $54.43/month ($1.81/day) in idle charges before serving anything.
A nightly Cloud Run job (1 vCPU/1 GiB, ~60 s): $0.0017 per run, $0.05/month — ~1000x less.

Break-even ~1.6 million predictions/day. Below that, batch is cheaper than keeping this
endpoint warm. At min-instances 0 there is no idle cost to amortise and the choice becomes
latency (16.6 s cold start vs hours of batch delay), not money.

Caveat: the free tier (180k vCPU-s, 360k GiB-s, 2M requests/month) is applied at Tier 1
prices and shared per billing account, so the actual bill for this lab is near zero.
These are the marginal rates past it.
