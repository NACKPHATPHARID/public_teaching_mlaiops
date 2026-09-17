# Lab 2 — Run comparison

Experiment `itcs355-lab2` · 17 runs · total estimated spend **0.52 THB** of 150 THB · instances: n1-standard-4

`thb_per_point` = cost per percentage point of val_roc_auc above the worst trial. Cheap improvements rank low; expensive improvements rank high, however good the headline number is.

## Hyperparameter study

| run_id | n_estimators | max_depth | min_samples_leaf | seed | val_roc_auc | test_roc_auc | billed_s | cost_thb | instance | job_id | thb_per_point |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 58e15293 | 100 | 4 | 5 | 20260101 | 0.8426 | 0.8533 | 60.0 | 0.038 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/8991901474585837568 | 0.02 |
| 4e78c3d3 | 100 | 4 | 1 | 20260101 | 0.8424 | 0.8518 | 61.0 | 0.0386 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/4366704657276338176 | 0.02 |
| 80f994ef | 300 | 4 | 5 | 20260101 | 0.8411 | 0.8545 | 61.0 | 0.0386 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/5343141351485603840 | 0.03 |
| f39b3b33 | 300 | 4 | 1 | 20260101 | 0.8404 | 0.8537 | 0.0 | 0.0 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/2653084999061864448 | 0.0 |
| 8d466c21 | 100 | 8 | 5 | 20260101 | 0.8397 | 0.8466 | 30.0 | 0.019 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/4911640212188168192 | 0.01 |
| 858f4bd4 | 300 | 8 | 5 | 20260101 | 0.8377 | 0.8491 | 31.0 | 0.0196 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/7014821238170189824 | 0.02 |
| d6ca3c6a | 300 | 12 | 5 | 20260101 | 0.8354 | 0.8431 | 30.0 | 0.019 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/653486764509364224 | 0.02 |
| 7f799d19 | 300 | 8 | 1 | 20260101 | 0.8338 | 0.8478 | 60.0 | 0.038 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/5195366988712509440 | 0.05 |
| 222edfde | 100 | 12 | 5 | 20260101 | 0.8322 | 0.8417 | 30.0 | 0.019 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/4776532223367053312 | 0.03 |
| 500aab1e | 100 | 8 | 1 | 20260101 | 0.8312 | 0.8488 | 60.0 | 0.038 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/5944371901739565056 | 0.08 |
| 6ea8f84f | 100 | 12 | 1 | 20260101 | 0.8268 | 0.8415 | 60.0 | 0.038 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/3508768928262258688 | 1.27 |
| 6b964e16 | 300 | 12 | 1 | 20260101 | 0.8265 | 0.8374 | 61.0 | 0.0386 | n1-standard-4 | projects/413557281673/locations/asia-southeast1/customJobs/3755622482837504000 |  |

Spread across the study (best − worst val_roc_auc): **0.0161**

## Seed variance for the chosen configuration

Configuration: `n_estimators=100, max_depth=4, min_samples_leaf=5` · 5 seeds

| run_id | seed | val_roc_auc | test_roc_auc | cost_thb |
|---|---|---|---|---|
| 61205a4d | 55 | 0.8936 | 0.8478 | 0.038 |
| c8524e86 | 33 | 0.8772 | 0.8409 | 0.038 |
| 262d4f9d | 44 | 0.8574 | 0.8743 | 0.019 |
| e9408a45 | 11 | 0.8553 | 0.8432 | 0.038 |
| 4b1d46d9 | 22 | 0.8509 | 0.8644 | 0.0386 |

- val_roc_auc: mean **0.8669**, std **0.0180**, range 0.8509–0.8936
- test_roc_auc: mean **0.8541**, std **0.0146**
- 12 of 12 study configurations are within 2 std (0.0361) of the best — those cannot be ranked apart by this evidence

## Pricing check

# Lab 2 — Pricing check

Date checked: 2026-09-17
Instance: n1-standard-4, region asia-southeast1 (Singapore)

Sources:
- On-demand / spot hourly rate: https://gcloud-compute.com/n1-standard-4.html
- USD→THB rate: https://www.xe.com/en-us/currencyconverter/convert/?Amount=1&From=USD&To=THB (1 USD = 33.33 THB, 2026-09-17)

| | USD/hour | THB/hour (at 33.33 THB/USD) |
|---|---|---|
| On-demand | $0.2344 | 7.81 THB |
| Spot | $0.0596 | 1.99 THB |

`src/costs.py` assumes on-demand = 7.6 THB/h and SPOT_FACTOR = 0.30 (spot = 2.28 THB/h).

- On-demand: matches closely (7.6 THB/h coded vs 7.81 THB/h actual — ~3% low, reasonable given exchange-rate drift and GCP's own rounding).
- Spot: coded rate runs high. Real spot pricing for n1-standard-4/asia-southeast1 is ~74.6% off on-demand ($0.0596/$0.2344), while the code's flat SPOT_FACTOR=0.30 assumes only a 70% discount — coded spot cost is ~15% above the real rate. So the study's logged spend (0.52 THB) is a conservative overestimate, not an underestimate: the actual bill would be lower, and the budget check was never at risk of a false pass.

## Which model did you register, and why?

# Which model did you register, and why?

We registered the top-ranked configuration (n_estimators=100, max_depth=4, min_samples_leaf=5, run 58e15293, val_roc_auc=0.8426), but that ranking is not meaningfully load-bearing: the entire 12-trial grid spans only 0.0161 val_roc_auc, and re-running this exact config across 5 seeds produced a spread of 0.0427 (mean 0.8669, std 0.0180) — larger than the whole grid. All 12 grid configurations fall within 2 standard deviations (0.0361) of the best score, so none can be distinguished from each other by this evidence; picking #1 over #4 (only 0.0022 apart) is essentially a coin flip. We kept it anyway because it's also cheap to train (~0.04 THB/run, ~60s billed spot time), so there's no cost trade-off to defend. Retraining monthly at this cost is under 0.05 THB/month — negligible. The main way this choice could be wrong: 5 seeds and 5 held-out rows are too small a sample to trust the variance estimate itself; a larger validation set or more seeds could shift which config looks best, or reveal the whole grid is within noise of a much simpler baseline.
