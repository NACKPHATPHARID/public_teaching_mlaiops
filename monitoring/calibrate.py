"""Lab 4: how much does PSI wobble when nothing is wrong?

    python -m monitoring.calibrate

Draws many "current" windows out of the clean data and scores each against the rest.
Two window shapes, because production traffic could look like either:
  rows      random readings from across the fleet (best case)
  machines  whole machines at a time, so a few machines dominate a window (worst case)
A threshold has to sit above this noise.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from monitoring.drift import ks_statistic, psi
from src import data


def null_scores(df: pd.DataFrame, window_rows: int, trials: int, seed: int, shape: str) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    machines = df[data.GROUP].unique()
    per_machine = max(1, len(df) // len(machines))
    take = max(2, window_rows // per_machine)
    rows = []
    for _ in range(trials):
        if shape == "machines":
            chosen = rng.choice(machines, size=take, replace=False)
            mask = df[data.GROUP].isin(chosen).to_numpy()
        else:
            mask = np.zeros(len(df), dtype=bool)
            mask[rng.choice(len(df), size=window_rows, replace=False)] = True
        cur, ref = df[mask], df[~mask]
        for feature in data.FEATURES:
            a = ref[feature].to_numpy(dtype=float)
            b = cur[feature].to_numpy(dtype=float)
            rows.append({"feature": feature, "psi": psi(a, b), "ks": ks_statistic(a, b)})
    return pd.DataFrame(rows)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference", type=Path, default=Path("data/raw/sensors.csv"))
    ap.add_argument("--trials", type=int, default=300)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    df = pd.read_csv(args.reference)
    table = {}
    for size in (1000, 3000):
        for shape in ("rows", "machines"):
            scores = null_scores(df, size, args.trials, args.seed, shape)
            table[f"{shape}/{size}"] = scores.groupby("feature")["psi"].quantile(0.99)
    print(f"PSI p99 on clean data ({args.trials} windows each), by window shape and size\n")
    print(pd.DataFrame(table).round(4).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
