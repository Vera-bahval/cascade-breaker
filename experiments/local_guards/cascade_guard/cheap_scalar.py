"""Execution-cost-only profile of the frozen N/M four-claim scalar baseline.

The caller retains the complete original input record/hash. This profile computes
only the four fixed claims against trusted_combined. It is a latency profile, not
a new ML block or a replacement for the full feature-extraction outputs.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import time

from . import cheap_nli as parent


PARENT_SHA256 = "8838fc1f84ff0b58868b768f5f3f683795c7a7b586748836bda4f79859d24b9d"
PROFILE = "fixed4_trusted_combined_only"
FIXED_CLAIM_IDS = ("fraud_completed", "hold_clear", "invariants_compliant", "policy_authorized")
VERSION = "cheap-scalar-profile-v1"


def verify_parent_source() -> str:
    actual = hashlib.sha256(Path(parent.__file__).read_bytes()).hexdigest()
    if actual != PARENT_SHA256:
        raise RuntimeError("Frozen cheap_nli parent source hash mismatch; scalar profile is invalid")
    return actual


def scalar_view(payload: dict) -> tuple[list[dict], dict]:
    """Select existing fields without mutating, reserializing, or changing the input hash."""
    sources = [source for source in payload["trusted_sources"]
               if source["source_id"] == "trusted_combined"]
    if len(sources) != 1:
        raise ValueError("Scalar profile requires exactly one trusted_combined source")
    claims = [claim for claim in payload["claims"] if claim["fixed"]]
    by_id = {claim["claim_id"]: claim for claim in claims}
    if (len(claims) != 4 or set(by_id) != set(FIXED_CLAIM_IDS)
            or any(claim["claim_type"] != claim["claim_id"] for claim in claims)):
        raise ValueError("Scalar profile requires the original four unique fixed claims")
    # Preserve original claim order, as in the frozen full extraction algorithm.
    return claims, sources[0]


class ScalarProfileAdapter(parent.NLIAdapter):
    def __init__(self, model_id, revision, model_dir, device="cpu"):
        parent_hash = verify_parent_source()
        super().__init__(model_id, revision, Path(model_dir), device)
        self.model_metadata.update(
            profile=PROFILE,
            profile_version=VERSION,
            parent_adapter_sha256=parent_hash,
            profile_adapter_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            input_identity="complete original record input_hash; view selection is model execution policy",
            profile_purpose="scalar baseline execution cost only; not a new ML block",
            scalar_claim_ids=list(FIXED_CLAIM_IDS),
            scalar_source_id="trusted_combined",
        )

    def score(self, record):
        claims, source = scalar_view(record["payload"])
        raw = []
        for claim in claims:
            if getattr(self, "deadline_ts", float("inf")) <= time.time():
                raise TimeoutError("Global cheap-guard deadline reached before complete scalar profile")
            plan = parent.pair_windows(self.tokenizer, source["text"], claim["text"], self.max_length)
            item = {**claim, "source_id": source["source_id"], "trust": source["trust"],
                    "status": plan["status"], "premise_tokens": plan["premise_tokens"],
                    "claim_tokens": plan["claim_tokens"], "windows": []}
            if plan["status"] != "OK":
                item["reason"] = plan["reason"]
            for window in plan["windows"]:
                if getattr(self, "deadline_ts", float("inf")) <= time.time():
                    raise TimeoutError("Global cheap-guard deadline reached before complete scalar profile")
                probabilities, cached = self.infer_ids(window["input_ids"])
                item["windows"].append({"start_token": window["start_token"],
                                        "end_token": window["end_token"],
                                        "pair_tokens": len(window["input_ids"]),
                                        "probabilities": probabilities, "cache_hit": cached})
            raw.append(item)
        return parent.aggregate(raw, self.block)


def create_adapter(model_id, revision, model_dir, device="cpu"):
    # __init__ checks the literal parent identity before any heavyweight load.
    return ScalarProfileAdapter(model_id, revision, Path(model_dir), device)
