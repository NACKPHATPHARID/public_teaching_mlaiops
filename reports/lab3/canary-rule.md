# Task 4 - canary detection rule (written before the canary ran)

Metric: share of /predict responses with probability above 0.5, i.e. the high-risk alert rate.
Computed from response bodies only, no labels needed. model_version is logged for the evidence
table afterwards and is not used by the detector.

Why this one: on the 1200-row test split v3 never exceeds 0.5 (0.00% against 2.33% for v2),
while mean p moves by 0.001 and Brier by 0.007. Expected requests to a 3-sigma shift are about
19k at 90/10 and about 760 at 50/50. Working in canary-prep.txt.

Traffic: held-out test rows, sampled with replacement, sent as single /predict calls.

Baseline r0: measured live over 3 minutes of 100% v2 traffic.

Alarm: after the 90/10 split, when the rate over all post-split requests falls below
r0 - 3*sqrt(r0*(1-r0)/n), with n the number of post-split requests. Checked every 5 s,
minimum n of 2000.

Action on alarm: route 100% back to model-v2 and record the split, alarm and rollback
timestamps.
