"""Lab 4 unit tests. Fast, no network, no dataset file needed."""
from __future__ import annotations

import pandas as pd
import pytest

from src import data


def _synthetic(machines: int = 50, per_machine: int = 6) -> pd.DataFrame:
    rows = []
    for i in range(machines * per_machine):
        row = {data.ID: i, data.GROUP: i // per_machine, data.TARGET: i % 2}
        row.update({f: 1.0 for f in data.FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)


def test_feature_list_never_contains_target_or_identifiers():
    for banned in (data.TARGET, data.GROUP, data.ID):
        assert banned not in data.FEATURES, f"{banned} must not be a model input"


def test_every_feature_is_in_the_schema_and_has_a_range():
    assert set(data.FEATURES) <= set(data.SCHEMA)
    assert set(data.FEATURES) == set(data.PLAUSIBLE_RANGES)


def test_load_raw_missing_file_tells_you_the_fix(tmp_path):
    with pytest.raises(FileNotFoundError, match="make data"):
        data.load_raw(tmp_path / "nope.csv")


def test_fingerprint_follows_content(tmp_path):
    a, b, c = (tmp_path / n for n in ("a.csv", "b.csv", "c.csv"))
    a.write_text("x\n1\n")
    b.write_text("x\n1\n")
    c.write_text("x\n2\n")
    assert data.data_fingerprint(a) == data.data_fingerprint(b)
    assert data.data_fingerprint(a) != data.data_fingerprint(c)


def test_split_shares_are_roughly_the_requested_fractions():
    df = _synthetic()
    train, val, test = data.split(df, seed=3)
    n = len(df)
    assert 0.1 <= len(val) / n <= 0.3, f"val share {len(val) / n:.2f}"
    assert 0.1 <= len(test) / n <= 0.3, f"test share {len(test) / n:.2f}"
    assert len(train) / n >= 0.4
