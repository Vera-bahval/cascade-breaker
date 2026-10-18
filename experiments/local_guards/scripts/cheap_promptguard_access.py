"""Bounded, anonymous official Prompt Guard 2 access preflight; never downloads weights.

This intentionally uses neither HF environment tokens nor credential files. It does
not accept gates or submit forms. Successful public files are pinned and hashed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.error
import urllib.request

MODEL_IDS = ("meta-llama/Llama-Prompt-Guard-2-22M", "meta-llama/Llama-Prompt-Guard-2-86M")
PUBLIC_FILES = ("README.md", "config.json", "tokenizer_config.json", "special_tokens_map.json",
                "tokenizer.json", "spm.model")
MAX_PUBLIC_BYTES = 20 * 1024 * 1024


def fetch(url: str, *, head: bool = False) -> tuple[dict, bytes | None]:
    """Keep only safe headers; do not print signed redirect locations or request IDs."""
    if not url.startswith("https://huggingface.co/"):
        raise ValueError("Only official Hugging Face endpoints are supported")
    request = urllib.request.Request(url, method="HEAD" if head else "GET",
                                     headers={"User-Agent": "cascade-cheapguard-access/1"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = b"" if head else response.read(MAX_PUBLIC_BYTES + 1)
            if len(data) > MAX_PUBLIC_BYTES:
                return {"status": response.status, "error": "public_file_size_limit"}, None
            meta = {"status": response.status, "bytes": len(data)}
            if not head:
                meta["sha256"] = hashlib.sha256(data).hexdigest()
            return meta, data
    except urllib.error.HTTPError as exc:
        return {"status": exc.code, "error_code": exc.headers.get("X-Error-Code"),
                "authentication_required": exc.code in (401, 403)}, None
    except urllib.error.URLError:
        return {"status": None, "error": "network_unavailable"}, None


def preflight(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for model_id in MODEL_IDS:
        row = {"model_id": model_id, "auth_mode": "anonymous_no_credential_lookup", "files": {}}
        api_result, data = fetch("https://huggingface.co/api/models/" + model_id)
        row["metadata_request"] = api_result
        if data is not None:
            metadata = json.loads(data)
            row.update({key: metadata.get(key) for key in ("sha", "gated", "private", "disabled")})
            row["siblings"] = [item["rfilename"] for item in metadata.get("siblings", [])]
        revision = row.get("sha")
        if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
            row["status"] = "UNKNOWN_METADATA_UNAVAILABLE"
            rows.append(row)
            continue
        directory = output / model_id.rsplit("/", 1)[-1] / revision
        directory.mkdir(parents=True, exist_ok=True)
        for filename in PUBLIC_FILES:
            result, content = fetch(f"https://huggingface.co/{model_id}/resolve/{revision}/{filename}")
            row["files"][filename] = result
            if content is not None:
                (directory / filename).write_bytes(content)
        weights = [name for name in row.get("siblings", []) if name.endswith(".safetensors")]
        row["weight_head"] = {}
        for filename in weights:
            result, _ = fetch(f"https://huggingface.co/{model_id}/resolve/{revision}/{filename}", head=True)
            row["weight_head"][filename] = result
        denied = any(item.get("status") in (401, 403) for item in row["files"].values())
        denied = denied or any(item.get("status") in (401, 403) for item in row["weight_head"].values())
        row["status"] = "BLOCKED_AUTH" if denied else "PUBLIC_ACCESS_PROBED"
        rows.append(row)
    report = {"schema": "cheap-promptguard-access-v1", "created_at": datetime.now(timezone.utc).isoformat(),
              "credentials_read": False, "forms_submitted": False, "weights_downloaded": False,
              "models": rows}
    (output / "access-preflight.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = preflight(args.output)
    print(json.dumps({"models": [{key: model.get(key) for key in ("model_id", "sha", "gated", "status")}
                                 for model in report["models"]]}))
