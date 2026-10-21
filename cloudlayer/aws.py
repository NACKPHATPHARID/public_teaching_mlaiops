"""AWS adapter. Only upload, download and invoke are done (Lab 5 swap test).

Needs: pip install boto3. Set AWS_ENDPOINT_URL to point at a local fake (moto) for testing.
BLOB_URI has to be an s3:// address for this adapter.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from cloudlayer.base import CloudAdapter


class AwsAdapter(CloudAdapter):
    def _client(self, name: str):
        import boto3

        return boto3.client(name, region_name=self.cfg.region)

    @staticmethod
    def _split(uri: str) -> tuple[str, str]:
        if not uri.startswith("s3://"):
            raise ValueError(f"AWS adapter needs an s3:// address, got {uri}")
        bucket, _, key = uri[len("s3://"):].partition("/")
        return bucket, key

    def upload(self, local_path: str, key: str) -> str:
        bucket, prefix = self._split(self.cfg.blob_uri)
        full_key = f"{prefix}/{key}".strip("/")
        self._client("s3").upload_file(
            local_path, bucket, full_key,
            ExtraArgs={"Tagging": urlencode(self.cfg.tags(1))},
        )
        return f"s3://{bucket}/{full_key}"

    def download(self, uri: str, local_path: str) -> None:
        bucket, key = self._split(uri)
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        self._client("s3").download_file(bucket, key, local_path)

    def invoke(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        resp = self._client("sagemaker-runtime").invoke_endpoint(
            EndpointName=endpoint,
            ContentType="application/json",
            Body=json.dumps(payload),
        )
        body = resp["Body"].read()
        try:
            return json.loads(body) if body else {}
        except ValueError:
            return {"raw": body.decode("utf-8", errors="replace")}

    def push_image(self, local_tag: str) -> str:
        raise NotImplementedError("not part of the swap test")


