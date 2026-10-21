#!/bin/sh
# usage: sh scripts/llm_run.sh NAME PROMPT_FILE MAX_OUTPUT_TOKENS
python scripts/llm_eval.py --golden evals/golden/machine-triage.jsonl --live \
  --system "$2" --max-output-tokens "$3" \
  --save-responses "evals/fixtures/machine-$1.jsonl" \
  --out "reports/llm_eval-machine-$1.json" \
  --baseline reports/llm_eval-machine-baseline.json | tee "reports/lab5/task9-$1.txt"
