"""Lab 3 Task 4 prep: which metric separates the canary (v3) from production (v2)?

Scores both models on the SAME held-out test split (same loader and split as src.train),
then estimates how many live requests a 90/10 or 50/50 canary needs before each metric
moves by 3 standard errors. Run BEFORE the canary, so the detection rule is chosen first.

    python scripts/compare_canary_lab3.py /tmp/m.joblib /tmp/v3/model.joblib
"""
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.metrics import brier_score_loss, roc_auc_score

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src import config, data, seeds  # noqa: E402

prod_path, canary_path = sys.argv[1:3]
cfg = config.load(strict=False)
seed = seeds.set_all(seeds.DEFAULT_SEED)
_, _, test_df = data.split(data.load_raw(cfg.raw_path), seed=seed)
X, y = test_df[data.FEATURES], test_df[data.TARGET].to_numpy()
print(f"test rows: {len(y)}   positive rate: {y.mean():.3f}\n")

models = {}
for name, path in (("v2 (prod)", prod_path), ("v3 (canary)", canary_path)):
    m = joblib.load(path)
    m.n_jobs = 1
    models[name] = m.predict_proba(X)[:, 1]

per_row = {  # per-request values a live monitor could average over a window
    "mean predicted p": lambda p: p,
    "share with p > 0.5": lambda p: (p > 0.5).astype(float),
    "Brier (needs label)": lambda p: (p - y) ** 2,
}

print(f"{'metric':24s} {'v2':>9s} {'v3':>9s} {'gap':>9s}")
for name, p in models.items():
    pass
p2, p3 = models["v2 (prod)"], models["v3 (canary)"]
print(f"{'ROC-AUC (needs label)':24s} {roc_auc_score(y, p2):9.4f} {roc_auc_score(y, p3):9.4f} "
      f"{roc_auc_score(y, p3) - roc_auc_score(y, p2):+9.4f}")
for label, f in per_row.items():
    a, b = f(p2).mean(), f(p3).mean()
    print(f"{label:24s} {a:9.4f} {b:9.4f} {b - a:+9.4f}")

print("\nRequests needed for the blended metric to move 3 standard errors:")
print(f"{'metric':24s} {'at 90/10':>10s} {'at 50/50':>10s}")
for label, f in per_row.items():
    a, b = f(p2), f(p3)
    gap = b.mean() - a.mean()
    sd = np.concatenate([a, b]).std()
    out = []
    for share in (0.10, 0.50):
        shift = abs(share * gap)
        out.append(float("inf") if shift == 0 else (3 * sd / shift) ** 2)
    print(f"{label:24s} {out[0]:10.0f} {out[1]:10.0f}")
