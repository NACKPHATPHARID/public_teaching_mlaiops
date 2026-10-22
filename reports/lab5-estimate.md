# Lab 5 cost estimate

Written on 21 Oct before building the pipeline. My estimate is 47 THB for everything tagged lab=5.

How I got there:
- Training: I timed one local run and it took 54 s. On a spot n1-standard-4 (1.99 THB/h from my Lab 2 check) I allow 4 min per run with container startup, for about 12 runs including failed ones. About 2 THB.
- Other pipeline steps (ingest, validate, evaluate, register, deploy): small containers, about 15 min per run in total, 12 runs. About 14 THB.
- Pipeline run fee: $0.03 per run from a pricing guide (nops.io), so about 12 THB for 12 runs. I will confirm it in the billing SKUs.
- Serving: Cloud Run staging scales to zero and I will only send a few test requests, then delete it. About 3 THB.
- Storage, registry and logs: small files for a few days. About 6 THB.
- LLM step: mostly recorded responses, a few live calls to measure tokens. About 10 THB.

The 20% band is 38 to 56 THB. What worries me most is extra debugging runs, since every failed run still costs a run fee, and leaving something on overnight.
