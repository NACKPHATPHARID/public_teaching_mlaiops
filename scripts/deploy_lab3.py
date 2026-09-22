"""Lab 3: deploy a registered model version through the adapter. Prints the endpoint URL."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cloudlayer.factory import get_adapter  # noqa: E402
from src import config  # noqa: E402

version, service, instance = sys.argv[1:4]
print(get_adapter(config.load()).deploy(version, service, instance))
