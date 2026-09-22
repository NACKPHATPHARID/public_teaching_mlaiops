"""Lab 3: three known payloads through adapter.invoke()."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloudlayer.factory import get_adapter  # noqa: E402
from src import config  # noqa: E402

PAYLOADS = {
    "typical": {"temp_c": 78.4, "vibration_mm_s": 3.1, "pressure_kpa": 315.2,
                "hours_since_service": 4200, "load_pct": 68.0, "ambient_humidity": 55.0},
    "hot_overdue": {"temp_c": 95.0, "vibration_mm_s": 7.5, "pressure_kpa": 340.0,
                    "hours_since_service": 9000, "load_pct": 92.0, "ambient_humidity": 70.0},
    "fresh_service": {"temp_c": 60.0, "vibration_mm_s": 1.2, "pressure_kpa": 300.0,
                      "hours_since_service": 100, "load_pct": 40.0, "ambient_humidity": 45.0},
}

adapter = get_adapter(config.load())
for name, payload in PAYLOADS.items():
    r = adapter.invoke(sys.argv[1], payload)
    assert 0.0 <= r["probability"] <= 1.0 and "model_version" in r, r
    print(f"{name:14s} p={r['probability']:.4f}  model_version={r['model_version']}")
print("smoke OK")
