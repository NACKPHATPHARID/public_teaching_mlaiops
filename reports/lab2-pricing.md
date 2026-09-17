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
