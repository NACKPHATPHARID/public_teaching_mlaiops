"""Lab 5: the managed training pipeline on Vertex AI Pipelines (KFP v2), and its submission.

No `from __future__ import annotations` here on purpose: KFP reads the annotations.
"""
import json
import os
import subprocess
import urllib.request
from pathlib import Path

from kfp import compiler, dsl

ENV_SLOTS = ("CLOUD_PROVIDER", "PROJECT_ID", "REGION", "BLOB_URI", "CONTAINER_REGISTRY",
             "MLFLOW_TRACKING_URI", "MODEL_REGISTRY_NAME", "IDENTITY_REF")

# Every script gets: $1 = output file, $2 = a, $3 = b.
PREP = 'mkdir -p "$(dirname "$1")" && '
INGEST = PREP + 'dvc pull && test -s data/raw/sensors.csv && sha256sum data/raw/sensors.csv > "$1"'
# Fails on a failed test AND on a skipped one: a skip here would mean "no data, no check".
VALIDATE = PREP + (
    'dvc pull && test -s data/raw/sensors.csv && { '
    'python -m pytest -q -rs tests/test_data.py > /tmp/t.txt 2>&1; rc=$?; cat /tmp/t.txt; '
    '[ $rc -eq 0 ] && ! grep -qi skipped /tmp/t.txt && echo ok > "$1"; }')
TRAIN = PREP + (
    'dvc pull && python -m src.train --no-track '
    '--metrics-out "$2/metrics.json" --model-out "$2/model" && echo done > "$1"')
# The gate exits 1 on a fail. Here we keep the verdict instead of crashing the run,
# so the condition below can skip register and deploy.
GATE = PREP + (
    'python scripts/evaluation_gate.py --metrics "$2/metrics.json" $3 --decision-out "$1"; '
    'tr -d "[:space:]" < "$1" > /tmp/d && cp /tmp/d "$1"')
REGISTER = PREP + 'python scripts/register.py --run-dir "$2" --run-id "$3" --version-out "$1"'
DEPLOY = PREP + (
    'printf %s "$2" > /tmp/v && python scripts/deploy.py --version-file /tmp/v && echo ok > "$1"')


def build(image: str, run_dir: str, env: dict):
    @dsl.container_component
    def sh(script: str, a: str, b: str, out: dsl.OutputPath(str)):
        return dsl.ContainerSpec(
            image=image, command=["/bin/sh", "-c"], args=[script, "step", out, a, b])

    @dsl.pipeline(name="itcs355-training-pipeline")
    def pipeline(incumbent_arg: str = "--incumbent-alias staging"):
        run = f"{run_dir}/{dsl.PIPELINE_JOB_ID_PLACEHOLDER}"
        ingest = sh(script=INGEST, a="-", b="-").set_display_name("ingest")
        validate = sh(script=VALIDATE, a="-", b="-").set_display_name("validate").after(ingest)
        train = sh(script=TRAIN, a=run, b="-").set_display_name("train").after(validate)
        train.set_cpu_limit("4").set_memory_limit("8G")
        gate = sh(script=GATE, a=run, b=incumbent_arg).set_display_name("evaluate").after(train)
        with dsl.If(gate.outputs["out"] == "pass"):
            reg = sh(script=REGISTER, a=run, b=dsl.PIPELINE_JOB_ID_PLACEHOLDER)
            reg.set_display_name("register")
            dep = sh(script=DEPLOY, a=reg.outputs["out"], b="-")
            dep.set_display_name("deploy_staging")
        for task in (ingest, validate, train, gate, reg, dep):
            for k, v in env.items():
                task.set_env_variable(k, v)

    return pipeline


def _token() -> str:
    return subprocess.run(["gcloud", "auth", "print-access-token"],
                          capture_output=True, text=True, check=True).stdout.strip()


def _git() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except Exception:
        return "unknown"


def compile_and_submit(spec=None, submit: bool = True):
    """PIPELINE_IMAGE = training image (digest form), SERVE_IMAGE_URI = serving image,
    PIPELINE_INCUMBENT_ARG = optional gate argument, e.g. '--incumbent 0.80'."""
    from cloudlayer.factory import get_adapter
    from src import config

    cfg = config.load()
    adapter = get_adapter(cfg)
    env = {k: os.environ[k] for k in ENV_SLOTS}
    env["SERVE_IMAGE_URI"] = os.environ["SERVE_IMAGE_URI"]
    env["LAB"] = "5"
    env["SERVING_SA"] = os.environ["SERVING_SA"]
    env["GIT_COMMIT"] = _git()

    run_dir = adapter._gcs_dir("lab5/runs")
    pipeline = build(os.environ["PIPELINE_IMAGE"], run_dir, env)
    out = Path("reports/lab5/pipeline.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    compiler.Compiler().compile(pipeline, package_path=str(out))
    if not submit:
        return str(out)

    pipeline_spec = json.loads(out.read_text())
    pipeline_spec = pipeline_spec.get("pipelineSpec", pipeline_spec)
    root = "gs://" + run_dir.removeprefix("/gcs/").replace("/runs", "/pipeline-root")
    params = {}
    if os.environ.get("PIPELINE_INCUMBENT_ARG"):
        params["incumbent_arg"] = {"stringValue": os.environ["PIPELINE_INCUMBENT_ARG"]}
    body = {
        "displayName": "itcs355-lab5-pipeline",
        "labels": {adapter._label(k): adapter._label(v) for k, v in cfg.tags(5).items()},
        "serviceAccount": os.environ.get("PIPELINE_SA", cfg.identity_ref),
        "runtimeConfig": {"gcsOutputDirectory": root, "parameterValues": {
            k: v["stringValue"] for k, v in params.items()}},
        "pipelineSpec": pipeline_spec,
    }
    url = (f"https://{cfg.region}-aiplatform.googleapis.com/v1/projects/{cfg.project_id}"
           f"/locations/{cfg.region}/pipelineJobs")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST", headers={
        "Authorization": f"Bearer {_token()}", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        job = json.loads(resp.read())
    print("submitted", job["name"])
    return job["name"]
