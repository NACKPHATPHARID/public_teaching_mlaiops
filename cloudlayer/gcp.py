"""GCP adapter. Implements upload/download/push_image for Lab 1 via gcloud + docker CLI.

Using subprocess + gcloud/docker CLI rather than the google-cloud-storage SDK, since
the SDK isn't in requirements.txt and this avoids adding an unpinned dependency
mid-lab. BLOB_URI is parsed here only, per the course rule (never in src/).
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import yaml

from cloudlayer.base import CloudAdapter


class GcpAdapter(CloudAdapter):
    def _bucket_and_prefix(self) -> tuple[str, str]:
        without_scheme = self.cfg.blob_uri.removeprefix("gs://")
        bucket, _, prefix = without_scheme.partition("/")
        return bucket, prefix

    def upload(self, local_path: str, key: str) -> str:
        bucket, prefix = self._bucket_and_prefix()
        dest = f"gs://{bucket}/{prefix}/{key}".replace("//", "/").replace("gs:/", "gs://")
        subprocess.run(
            ["gcloud", "storage", "cp", local_path, dest],
            check=True,
        )
        return dest

    def download(self, uri: str, local_path: str) -> None:
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["gcloud", "storage", "cp", uri, local_path],
            check=True,
        )

    def download_key(self, key: str, local_path: str) -> None:
        """Like download(), but takes a key relative to BLOB_URI instead of a full URI — for
        callers (src/tune.py) that never held a URI in the first place, since the job wrote
        its output via the auto-mounted /gcs/ path, not through upload(). Keeps the actual
        gs:// string construction inside cloudlayer/, per the course's portability rule."""
        bucket, prefix = self._bucket_and_prefix()
        uri = f"gs://{bucket}/{prefix}/{key}".replace("//", "/").replace("gs:/", "gs://")
        self.download(uri, local_path)

    def push_image(self, local_tag: str) -> str:
        image_name, _, tag = local_tag.partition(":")
        remote_tag = f"{self.cfg.container_registry}/{image_name}:{tag}"

        subprocess.run(["docker", "tag", local_tag, remote_tag], check=True)
        subprocess.run(["docker", "push", remote_tag], check=True)

        out = subprocess.run(
            ["gcloud", "artifacts", "docker", "images", "describe", remote_tag,
             "--format=value(image_summary.digest)"],
            capture_output=True, text=True, check=True,
        )
        digest = out.stdout.strip()
        repo = remote_tag.split(":")[0]
        return f"{repo}@{digest}"

    # =============================================================================================
    # Lab 2 — managed training (Vertex AI custom jobs) and model registry (Vertex Model Registry)
    # =============================================================================================

    TERMINAL_STATES = {"JOB_STATE_SUCCEEDED", "JOB_STATE_FAILED", "JOB_STATE_CANCELLED",
                       "JOB_STATE_EXPIRED"}
    SKLEARN_SERVING_IMAGE = "asia-docker.pkg.dev/vertex-ai/prediction/sklearn-cpu.1-5:latest"

    def _gcs_dir(self, key: str) -> str:
        """A key relative to BLOB_URI, as a /gcs/... path — Vertex mounts your bucket there
        automatically inside every custom job, so the container just reads/writes plain files;
        no client library, no credentials handling. See docs.cloud.google.com/vertex-ai/docs/
        training/cloud-storage-file-system."""
        bucket, prefix = self._bucket_and_prefix()
        return f"/gcs/{bucket}/{prefix}/{key}".replace("//", "/")

    @staticmethod
    def _label(value: Any) -> str:
        """GCP label/alias values: lowercase letters, digits, '-', '_', max 63 chars."""
        return re.sub(r"[^a-z0-9_-]", "-", str(value).lower())[:63]

    @staticmethod
    def _flag(key: str, value: Any) -> list[str]:
        """One hyperparam -> one or more argv tokens, matching argparse's own conventions:
        a bool becomes a bare store_true flag (present or absent), everything else --key value."""
        flag = f"--{key.replace('_', '-')}"
        if isinstance(value, bool):
            return [flag] if value else []
        return [flag, str(value)]

    def submit_training(self, image_uri: str, args: dict[str, Any]) -> str:
        """Submit one custom job. `args`:

            module        str    e.g. "src.train" — run as `python -m <module>`
            hyperparams   dict   -> --n-estimators 300 --max-depth 8 ... (bools become flags)
            output_key    str    where metrics.json/model.joblib land, relative to BLOB_URI
            instance      str    machine type, e.g. n1-standard-4
            spot          bool   discounted (preemptible) compute
            labels        dict   cost attribution + `make teardown`
            env           dict   extra container env vars (e.g. GIT_COMMIT)
            display_name  str
        Returns the full job resource name (what wait_training/cancel_training expect).
        """
        out_dir = self._gcs_dir(args["output_key"])
        argv = [t for k, v in args.get("hyperparams", {}).items() for t in self._flag(k, v)]
        argv += ["--metrics-out", f"{out_dir}/metrics.json", "--model-out", f"{out_dir}/model"]

        env = {"PYTHONUNBUFFERED": "1", **args.get("env", {})}
        labels = {self._label(k): self._label(v) for k, v in
                 {**self.cfg.tags(2), **args.get("labels", {})}.items()}

        config_yaml = {
            "workerPoolSpecs": [{
                "machineSpec": {"machineType": args.get("instance", "n1-standard-4")},
                "replicaCount": 1,
                "containerSpec": {
                    "imageUri": image_uri,
                    # dvc pull needs the pointer file + remote config baked into the image
                    # (Dockerfile copies .dvc/config and data/raw.dvc); "$@" forwards the argv
                    # given after "--" below to the module, unquoted per-token (no shell
                    # re-escaping needed — each stays a single argv entry).
                    "command": ["/bin/sh", "-c", f'dvc pull && python -m {args["module"]} "$@"'],
                    "args": ["--", *argv],
                    "env": [{"name": k, "value": str(v)} for k, v in env.items()],
                },
            }],
            # Run-time identity. NOT the identity that submits the job (that is you).
            "serviceAccount": self.cfg.identity_ref,
            "scheduling": {"strategy": "SPOT" if args.get("spot", True) else "STANDARD"},
        }

        config_path = Path.home() / ".itcs355_lab2_job.yaml"
        config_path.write_text(yaml.safe_dump(config_yaml, sort_keys=False))

        result = subprocess.run(
            ["gcloud", "ai", "custom-jobs", "create",
             "--region", self.cfg.region,
             "--display-name", args.get("display_name", "itcs355-lab2"),
             "--labels", ",".join(f"{k}={v}" for k, v in labels.items()),
             "--config", str(config_path)],
            capture_output=True, text=True, check=True,
        )
        match = re.search(r"projects/[\w-]+/locations/[\w-]+/customJobs/\d+",
                          result.stdout + result.stderr)
        if not match:
            raise RuntimeError(f"could not parse job id from output:\n{result.stdout}\n{result.stderr}")
        return match.group(0)

    def wait_training(self, job_id: str, poll_s: int = 20) -> dict[str, Any]:
        """Block until the job reaches a terminal state."""
        def ts(s: str | None):
            from datetime import datetime
            return datetime.fromisoformat(s.replace("Z", "+00:00")) if s else None

        while True:
            result = subprocess.run(
                ["gcloud", "ai", "custom-jobs", "describe", job_id,
                 "--region", self.cfg.region, "--format=json"],
                capture_output=True, text=True, check=True,
            )
            info = json.loads(result.stdout)
            state = info.get("state", "JOB_STATE_UNSPECIFIED")
            if state in self.TERMINAL_STATES:
                start, end = ts(info.get("startTime")), ts(info.get("endTime"))
                created = ts(info.get("createTime"))
                return {
                    "job_id": job_id,
                    "state": state,
                    "succeeded": state == "JOB_STATE_SUCCEEDED",
                    # Billable time is roughly start -> end; queue time (create -> start) isn't.
                    "duration_s": (end - start).total_seconds() if start and end else 0.0,
                    "queued_s": (start - created).total_seconds() if start and created else 0.0,
                    "error": (info.get("error") or {}).get("message", ""),
                    "console_url": (f"https://console.cloud.google.com/vertex-ai/locations/"
                                    f"{self.cfg.region}/training/{job_id.rsplit('/', 1)[-1]}"
                                    f"?project={self.cfg.project_id}"),
                }
            print(f"  job {job_id.rsplit('/', 1)[-1]}: {state}", flush=True)
            time.sleep(poll_s)

    def cancel_training(self, job_id: str) -> None:
        """Used to simulate a spot interruption, and by teardown."""
        subprocess.run(["gcloud", "ai", "custom-jobs", "cancel", job_id,
                        "--region", self.cfg.region], capture_output=True, text=True)

    # --- Lab 2: registry -------------------------------------------------------------------------
    def _find_model(self, name: str) -> str | None:
        """Full resource name of an existing model with this display name, or None."""
        out = subprocess.run(
            ["gcloud", "ai", "models", "list", "--region", self.cfg.region,
             "--filter", f"displayName={name}", "--format=value(name)"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        return out.splitlines()[0] if out else None

    def register_model(self, model_uri: str, name: str, labels: dict[str, Any] | None = None,
                       aliases: list[str] | None = None) -> str:
        """Upload a new version to Vertex Model Registry. `model_uri` must be a real gs://
        directory containing the model file (the plain model.joblib src.train wrote, not
        MLflow's own local artifact copy — that one never leaves your laptop). Returns the
        Vertex version id as a string.

        Lineage goes on the VERSION as labels (sanitised — GCP label values can't hold '.',
        ':' or a 64-char digest) and verbatim in the version description, which can.
        """
        labels = labels or {}
        parent = self._find_model(name)
        cmd = [
            "gcloud", "ai", "models", "upload",
            "--region", self.cfg.region,
            "--display-name", name,
            "--artifact-uri", model_uri,
            "--container-image-uri", self.SKLEARN_SERVING_IMAGE,
            "--labels", ",".join(f"{self._label(k)}={self._label(v)}" for k, v in labels.items()),
            "--version-description", "\n".join(f"{k}={v}" for k, v in labels.items())[:2000],
        ]
        if parent:
            cmd += ["--parent-model", parent]
        if aliases:
            cmd += ["--version-aliases", ",".join(aliases)]

        out = subprocess.run(cmd, capture_output=True, text=True, check=True)
        match = re.search(r"/models/[\w-]+@(\d+)", out.stdout + out.stderr) or \
            re.search(r"Model Version number:\s*(\d+)", out.stdout + out.stderr)
        if not match:
            raise RuntimeError(f"could not parse model version from output:\n{out.stdout}\n{out.stderr}")
        return match.group(1)

    def set_model_alias(self, name: str, version: str, alias: str) -> None:
        """Promotion. gcloud has no CLI verb to change aliases on an existing version, so this
        is the one place we call the REST API directly (Vertex's own `mergeVersionAliases`).
        An alias is unique per model, so adding it here moves it off whatever version had it —
        exactly the semantics a 'staging' pointer should have."""
        import urllib.request

        model = self._find_model(name)
        if not model:
            raise RuntimeError(f"no model named {name!r} in the registry yet")
        token = subprocess.run(["gcloud", "auth", "print-access-token"],
                               capture_output=True, text=True, check=True).stdout.strip()
        url = (f"https://{self.cfg.region}-aiplatform.googleapis.com/v1/"
               f"{model}@{version}:mergeVersionAliases")
        req = urllib.request.Request(
            url, method="POST",
            data=json.dumps({"versionAliases": [alias]}).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            resp.read()

    # --- teardown (minimal, Lab 2 scope) ----------------------------------------------------------
    def teardown(self, tags: dict[str, str]) -> list[str]:
        """Cancel still-running custom jobs carrying these labels. Finished jobs cost nothing;
        the registered model and bucket stay — Lab 3 needs them."""
        flt = " AND ".join(f"labels.{self._label(k)}={self._label(v)}" for k, v in tags.items())
        out = subprocess.run(
            ["gcloud", "ai", "custom-jobs", "list", "--region", self.cfg.region,
             "--filter", flt, "--format=value(name,state)"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        cancelled = []
        for line in filter(None, out.splitlines()):
            job_id, state = line.split()
            if state not in self.TERMINAL_STATES:
                self.cancel_training(job_id)
                cancelled.append(job_id)
        return cancelled
