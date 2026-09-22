# Lab 3 Task 4 — canary detection rule (stated BEFORE the canary runs)

- Metric: share of /predict responses with probability > 0.5 ("high-risk alert rate").
  Label-free; computed from response bodies only. model_version is logged for evidence
  but is NOT used by the detector.
- Why this metric: offline on the 1,200-row test split, v3 never exceeds 0.5 (0.00% vs
  2.33% for v2), while mean p (+0.001) and Brier (+0.007) barely move. Expected requests
  to a 3-sigma shift: ~19k at 90/10, ~760 at 50/50 (reports/lab3/canary-prep.txt).
- Traffic: held-out test rows, sampled with replacement, as single /predict calls.
- Baseline r0: measured live over 3 minutes of 100% v2 traffic.
- Alarm: after the 90/10 split, when the rate over all post-split requests falls below
  r0 - 3 * sqrt(r0 * (1 - r0) / n), with n = number of post-split requests (checked every 5 s,
  minimum n = 2000).
- Action on alarm: route 100% back to model-v2; record timestamps of split, alarm, rollback.
