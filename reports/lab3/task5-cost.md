# Task 5 - cost per 1000 predictions

Cloud Run, request-based billing. asia-southeast1 is Tier 2, so rates are 1.4x the Tier 1
list prices. Checked against cloud.google.com/run/pricing on 23 Sep 2026.

| item                  | Tier 1     | Tier 2 (used here) |
|-----------------------|------------|--------------------|
| CPU active            | 0.000024   | 0.0000336 /vCPU-s  |
| memory active         | 0.0000025  | 0.0000035 /GiB-s   |
| CPU + memory idle     | 0.0000025  | 0.0000035 each     |
| requests              | 0.40/M     | 0.40/M             |

1 vCPU / 1 GiB works out to $0.1336 per instance-hour serving, $0.0252 idle.

## Method

  cost per 1000 = (instances * 3600 * [u*active + (1-u)*idle]) / (u * RPS * 3600) * 1000 + requests

RPS = 151.9, measured at 10 users on the config that meets the p95 target (1 vCPU,
n_jobs=1, --concurrency 4, 3 warm instances, p95 86 ms).

## Utilisation assumption: 30% average busy

| u    | $/hour | preds/hour | $ per 1000 |
|------|--------|------------|------------|
| 100% | 0.4007 | 546,840    | 0.00113    |
| 30%  | 0.1731 | 164,052    | 0.00146    |
| 10%  | 0.1081 | 54,684     | 0.00238    |
| 1%   | 0.0789 | 5,468      | 0.01482    |

This is the fragile part. The number moves 13x between 1% and 100% because the three warm
instances bill at the idle rate whenever nobody calls, so at low traffic you are paying for
readiness rather than predictions.

At min-instances 0 it is $0.00113 per 1000 whatever the utilisation, but every idle gap then
costs a 16.6 s cold start. About $54/month of idle charges is the price of removing that.

## Instance size

| config         | ceiling  | $/hour (3 busy) | $ per 1000 |
|----------------|----------|-----------------|------------|
| 1 vCPU / 1 GiB | ~75 RPS  | 0.401           | 0.00188    |
| 2 vCPU / 2 GiB | ~115 RPS | 0.801           | 0.00234    |

Double the price for 1.5x the throughput and no latency gain, so 24% more per prediction.
Scale out, not up.

## Batch vs warm endpoint

Three warm instances cost $54.43/month ($1.81/day) in idle charges before serving anything.
A nightly Cloud Run job at 1 vCPU / 1 GiB for about a minute costs $0.0017 per run, so
$0.05/month, roughly a thousand times less.

Break-even is around 1.6 million predictions a day. Below that, batch is cheaper than keeping
this endpoint warm. At min-instances 0 there is no idle cost to amortise, so the choice
becomes latency (16.6 s cold start versus hours of batch delay) rather than money.

Note: the free tier (180k vCPU-s, 360k GiB-s, 2M requests a month) is applied at Tier 1 prices
and shared per billing account, so the real bill for this lab is close to zero. These are the
marginal rates past it.
