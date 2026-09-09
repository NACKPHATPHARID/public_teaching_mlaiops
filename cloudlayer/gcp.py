"""GCP adapter. Implements upload/download/push_image for Lab 1 via gcloud + docker CLI.

Using subprocess + gcloud/docker CLI rather than the google-cloud-storage SDK, since
the SDK isn't in requirements.txt and this avoids adding an unpinned dependency
mid-lab. BLOB_URI is parsed here only, per the course rule (never in src/).
"""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

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
