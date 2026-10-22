# Lab 5 - Cost report

Provider `gcp` · instance `cloud-run-1vcpu-1gib` · 4.50 THB/hour

## 1. Estimate, made before running
47.00 THB

## 2. Actual, from billing filtered by tag
4.92 THB

## 3. The gap
My estimate was 47 THB and the real cost was 4.92 THB, so I guessed 42.08 THB too high by a lot. I kept the 47 because I wrote it before running anything (reports/lab5-estimate.md). This is where I was wrong:

- Pipeline run fee: I guessed 12 runs at about 1 THB each, so 12 THB. Billing shows only 4 runs, 4.03 THB. Those 4 include the runs that failed.
- Machines for training and the other steps: I guessed 16 THB, the real number is 0.59 THB. The whole pipeline only ran 8 to 11 minutes on small machines.
- Serving: I guessed 3 THB, the real number is 0.31 THB. Staging only ran for a few minutes and then I deleted it.
- Storage, registry and logs: I guessed 6 THB but nothing is tagged lab=5. Over the whole term the registry cost 3.51 THB and storage 0.03 THB, but they have no lab tag.
- LLM step: I guessed 10 THB and it does not show under lab=5. By my token counts one live run of the 15 golden cases costs about 0.08 THB.

That adds up to about 42 THB. Nothing was left running overnight. Next time I will check the run fee and machine sizes in Billing before guessing.

If I guessed again now it would be 4 runs x 1 THB, plus 0.6 THB for machines and 0.3 THB for serving, about 5 THB. That is within 20% of the real 4.92 THB, but I made it after the fact so it does not count as my estimate.

Billing shows the cost before credits. Because of the free trial credit I paid 0 THB. The whole term for all labs was about 24 THB before credits.

## 4. Breakdown
Training machines: 0.59 THB (cores 0.33, RAM 0.18, disk 0.08)
Storage: 0.00 THB, nothing is tagged lab=5
Serving (Cloud Run): 0.31 THB
Pipeline run fee: 4.03 THB
Monitoring: 0.00 THB, I did not use any
Total: 4.93 THB, billing says 4.92 THB, the difference is rounding

## 5. Cost per 1,000 predictions
Speed: my Lab 3 load test gave 151.9 requests per second with 3 warm instances, so about 50.6 per instance. I priced one instance (cloud-run-1vcpu-1gib, 4.5 THB per hour, worked out from my Lab 5 billing).

At 5% busy: 0.4941 THB per 1,000 predictions
At 25% busy: 0.0988 THB per 1,000 predictions
At 80% busy: 0.0309 THB per 1,000 predictions

I believe the 5% one, because staging only got a handful of test requests. Busy time is the least certain number here, which is why I show three.

Below about 0.0012 requests per second, scheduled batch is cheaper than keeping the endpoint warm. My real traffic was 4 requests in total, which over a week is about 0.000007 per second, far below that. So for traffic like mine, batch (or scale to zero, which staging already did) is the cheaper choice.

## 6. One optimisation I applied
I made the LLM triage step cheaper by asking for shorter reasons in the prompt and setting max_output_tokens to 50.

Before (prompt v1, no cap): 5.03 THB per 1,000 requests, p95 latency 2156 ms.
After (prompt v4-short and cap 50): 4.23 THB per 1,000 requests, p95 latency 1474 ms. That is 15.9% cheaper.

All 15 golden cases still pass the gate, so quality did not drop. The cap alone only saved 0.15 THB and broke 5 cases, so I did not use it alone. Latency also looks better, but some of the slow time in the first run was Google rate limiting me and my retries, so I would not claim all of it.
