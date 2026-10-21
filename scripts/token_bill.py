"""Lab 5 Task 9: the token-cost figures, computed from the saved eval reports."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.llmcost import Usage, cache_breakeven_hit_rate, cost_per_1k_requests, token_rates  # noqa: E402

PROVIDER, MODEL = "gcp", "small"
rin, rout = token_rates(PROVIDER, MODEL)
print(f"rates: {rin} THB in, {rout} THB out, per 1M tokens\n")

costs = {}
for name in ("baseline", "cap50", "shortcap50"):
    r = json.loads(Path(f"reports/llm_eval-machine-{name}.json").read_text())
    u = Usage(r["avg_input_tokens"], r["avg_output_tokens"])
    costs[name] = cost_per_1k_requests(PROVIDER, MODEL, u)
    print(f"{name:11} in={u.input_tokens} out={u.output_tokens} "
          f"pass={r['passed']}/{r['cases']} THB per 1k = {costs[name]:.4f}")

saved = costs["baseline"] - costs["shortcap50"]
print(f"\nsaving, shorter reasons + cap: {saved:.4f} THB per 1k "
      f"({saved / costs['baseline']:.1%})")
print(f"saving, cap alone:             {costs['baseline'] - costs['cap50']:.4f} THB per 1k "
      "(but 5 cases broke)")

prefix = 300  # about the fixed system prompt: shortest request was 320 tokens in total
print(f"\ncache break-even hit rate for a {prefix}-token prefix: "
      f"{cache_breakeven_hit_rate(PROVIDER, MODEL, prefix):.1%}")
