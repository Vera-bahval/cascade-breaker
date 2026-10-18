"""CPU-first pinned NLI/MiniCheck adapters. Imports never load a model."""
from __future__ import annotations

import math
import time
from collections import defaultdict
from pathlib import Path

MODELS = {
    "cross-encoder/nli-deberta-v3-base": {"block": "N", "revision": "6c749ce3425cd33b46d187e45b92bbf96ee12ec7", "labels": {0: "contradiction", 1: "entailment", 2: "neutral"}},
    "lytang/MiniCheck-DeBERTa-v3-Large": {"block": "M", "revision": "2f2d01a54fa022a7ffadb76260e1ea8bc88c82bb", "labels": {0: "unsupported", 1: "supported"}},
}
VERSION = "cheap-nli-v1"


def pair_windows(tokenizer, premise, claim, max_length=512, overlap=64):
    """Full claim in each pair; token-exact complete premise coverage, no decode/reencode."""
    p = tokenizer.encode(premise, add_special_tokens=False)
    c = tokenizer.encode(claim, add_special_tokens=False)
    budget = max_length - len(c) - tokenizer.num_special_tokens_to_add(pair=True)
    if budget <= 0 or (len(p) > budget and budget <= overlap):
        return {"status": "UNKNOWN", "reason": "claim_exceeds_window_budget", "claim_tokens": len(c), "premise_tokens": len(p), "windows": []}
    windows = []
    start = 0
    while True:
        stop = min(start + budget, len(p))
        ids = tokenizer.build_inputs_with_special_tokens(p[start:stop], c)
        if len(ids) > max_length:
            raise ValueError("Tokenizer pair builder exceeded declared budget")
        windows.append({"start_token": start, "end_token": stop, "input_ids": ids, "attention_mask": [1] * len(ids)})
        if stop >= len(p):
            break
        start = stop - overlap
    return {"status": "OK", "claim_tokens": len(c), "premise_tokens": len(p), "windows": windows}


def aggregate(raw, block):
    """Frozen distributions -> numeric features; no label/calibration inputs accepted."""
    labels = ("entailment", "contradiction", "neutral") if block == "N" else ("supported", "unsupported")
    support_key = "entailment" if block == "N" else "supported"
    features, groups = {}, defaultdict(list)
    for source in ("trusted_policy", "trusted_native", "trusted_combined", "untrusted_premise"):
        for claim_type in ("fraud_completed", "hold_clear", "invariants_compliant", "policy_authorized"):
            groups[source + "." + claim_type] = []
    for source in ("trusted_combined", "untrusted_premise"):
        groups[source + ".explanation_sentence"] = []
    fixed_support = {}
    missing_fixed = False
    for item in raw:
        key = item["source_id"] + "." + item["claim_type"]
        values = item["windows"]
        known = item["status"] == "OK" and bool(values)
        groups[key].append((item, known))
        if item["fixed"] and item["source_id"] == "trusted_combined":
            if known:
                fixed_support[item["claim_id"]] = max(w["probabilities"][support_key] for w in values)
            else:
                missing_fixed = True
    for key, items in groups.items():
        known_items = [i for i, known in items if known]
        features[key + ".missingness"] = 1 - len(known_items) / len(items) if items else 1.0
        for label in labels:
            claim_maxima = [max(w["probabilities"][label] for w in i["windows"]) for i in known_items]
            window_values = [w["probabilities"][label] for i in known_items for w in i["windows"]]
            features[key + "." + label + ".max"] = max(claim_maxima, default=-1.0)
            features[key + "." + label + ".mean"] = sum(window_values) / len(window_values) if window_values else -1.0
    features["explanation_sentence.missingness"] = float(not any(i["claim_type"] == "explanation_sentence" for i in raw))
    risk = None if missing_fixed or len(fixed_support) != 4 else max(1 - x for x in fixed_support.values())
    return {"status": "UNKNOWN" if any(i["status"] != "OK" for i in raw) else "OK", "features": features, "scalar_risk": risk, "window_count": sum(len(i["windows"]) for i in raw), "raw": raw}


class NLIAdapter:
    def __init__(self, model_id, revision, model_dir, device="cpu"):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        spec = MODELS[model_id]
        if revision != spec["revision"]:
            raise ValueError("Unexpected revision for preregistered model")
        self.block = spec["block"]
        self.labels = spec["labels"]
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, use_fast=False)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir, local_files_only=True, torch_dtype=torch.float32).eval().to(device)
        id2label = {int(k): v.lower() for k, v in self.model.config.id2label.items()}
        expected = spec["labels"] if self.block == "N" else {0: "0", 1: "1"}
        if id2label != expected:
            raise ValueError(f"Official classifier label map mismatch: {id2label}")
        self.device = device
        self.max_length = 512
        self.model_metadata = {"adapter_version": VERSION, "model_id": model_id, "revision": revision, "device": device, "dtype": "float32", "labels": self.labels, "parameter_count": sum(p.numel() for p in self.model.parameters()), "eval_mode": not self.model.training, "max_pair_tokens": 512, "overlap": 64, "pair_format": "[CLS] document [SEP] claim [SEP]", "label_source": "pinned HF config + official model card; MiniCheck supported=1 unsupported=0", "window_support_aggregation": "max"}
        self._cache = {}
        self.feature_template = aggregate([], self.block)["features"]

    def infer_ids(self, ids):
        import torch
        key = tuple(ids)
        tensor = torch.tensor([ids], dtype=torch.long, device=self.device)
        with torch.inference_mode():
            logits = self.model(input_ids=tensor, attention_mask=torch.ones_like(tensor)).logits[0]
            probabilities = logits.softmax(dim=-1).float().cpu().tolist()
        if not all(math.isfinite(x) for x in probabilities):
            raise ValueError("Nonfinite classifier output")
        result = {label: probabilities[i] for i, label in self.labels.items()}
        # Exact token-pair cache only; source/window/claim distributions are still written.
        return result, False

    def score(self, record):
        payload = record["payload"]
        sources = payload["trusted_sources"] + [{"source_id": "untrusted_premise", "trust": "untrusted supplier and agent assertions", "text": payload["untrusted_premise"]}]
        raw = []
        for claim in payload["claims"]:
            for source in sources:
                # Sentence grounding uses combined trusted evidence and the separate
                # untrusted premise; fixed claims additionally expose each trust source.
                if not claim["fixed"] and source["source_id"] not in ("trusted_combined", "untrusted_premise"):
                    continue
                plan = pair_windows(self.tokenizer, source["text"], claim["text"], self.max_length)
                item = {**claim, "source_id": source["source_id"], "trust": source["trust"], "status": plan["status"], "premise_tokens": plan["premise_tokens"], "claim_tokens": plan["claim_tokens"], "windows": []}
                if plan["status"] != "OK":
                    item["reason"] = plan["reason"]
                for window in plan["windows"]:
                    if getattr(self, "deadline_ts", float("inf")) <= time.time():
                        raise TimeoutError("Global cheap-guard deadline reached before complete prefix coverage")
                    probs, cached = self.infer_ids(window["input_ids"])
                    item["windows"].append({"start_token": window["start_token"], "end_token": window["end_token"], "pair_tokens": len(window["input_ids"]), "probabilities": probs, "cache_hit": cached})
                raw.append(item)
        return aggregate(raw, self.block)


def create_adapter(model_id, revision, model_dir, device="cpu"):
    return NLIAdapter(model_id, revision, Path(model_dir), device)


def probe_mps(adapter, examples):
    """Six preselected short/long pairs, CPU FP32 reference then 3 A/A repeats.

    One model is moved between devices, preserving the one-heavy-process budget.
    Any error, >1e-4 probability delta or changed argmax falls back to CPU.
    """
    import torch
    plans = [pair_windows(adapter.tokenizer, p, c)["windows"] for p, c in examples]
    ids = [w[0]["input_ids"] for w in plans if w]
    if len(ids) != 6:
        raise ValueError("MPS probe requires exactly six usable short/long pairs")
    adapter._cache.clear()
    adapter.model.to("cpu"); adapter.device = "cpu"
    from .cheap_inputs import digest
    cpu_repeats = [[adapter.infer_ids(x)[0] for x in ids] for _ in range(3)]
    cpu = cpu_repeats[0]
    result = {"probe_input_hashes": [digest({"premise": p, "claim": c}) for p, c in examples], "pair_token_lengths": list(map(len, ids)), "cpu_reference": cpu, "cpu_repeats": cpu_repeats, "tolerance": 1e-4, "aa_tolerance": 1e-4, "repeats": 3, "max_delta": 0.0, "cpu_aa_delta": 0.0, "mps_aa_delta": 0.0, "argmax_changed": False, "passed": False, "selected_device": "cpu"}
    def validate_distributions(repeats):
        return all(all(math.isfinite(v) and 0 <= v <= 1 for v in x.values()) and abs(sum(x.values()) - 1) <= 1e-5 and set(x) == set(adapter.labels.values()) for repeat in repeats for x in repeat)
    for repeat in cpu_repeats:
        for a, b in zip(cpu, repeat):
            result["cpu_aa_delta"] = max(result["cpu_aa_delta"], max(abs(a[k] - b[k]) for k in a))
            result["argmax_changed"] |= max(a, key=a.get) != max(b, key=b.get)
    result["cpu_valid"] = validate_distributions(cpu_repeats)
    if not result["cpu_valid"] or result["cpu_aa_delta"] > 1e-4 or result["argmax_changed"]:
        raise ValueError("CPU FP32 A/A failed distribution/repeat validation")
    if not torch.backends.mps.is_available():
        result["reason"] = "MPS unavailable"
        return result
    try:
        adapter.model.to("mps"); adapter.device = "mps"
        for _ in range(3):
            if getattr(adapter, "deadline_ts", float("inf")) <= time.time():
                raise TimeoutError("Global deadline during MPS equivalence gate")
            adapter._cache.clear()
            mps = [adapter.infer_ids(x)[0] for x in ids]
            result.setdefault("mps_repeats", []).append(mps)
            for a, b in zip(cpu, mps):
                result["max_delta"] = max(result["max_delta"], max(abs(a[k] - b[k]) for k in a))
                result["argmax_changed"] |= max(a, key=a.get) != max(b, key=b.get)
        for repeat in result["mps_repeats"]:
            for a, b in zip(result["mps_repeats"][0], repeat):
                result["mps_aa_delta"] = max(result["mps_aa_delta"], max(abs(a[k] - b[k]) for k in a))
        result["mps_valid"] = validate_distributions(result["mps_repeats"])
        result["passed"] = result["max_delta"] <= 1e-4 and result["mps_aa_delta"] <= 1e-4 and result["mps_valid"] and not result["argmax_changed"]
        result["selected_device"] = "mps" if result["passed"] else "cpu"
    except Exception as exc:
        result["reason"] = f"{type(exc).__name__}: {exc}"
    adapter.device = result["selected_device"]
    adapter.model.to(adapter.device)
    adapter.model_metadata["device"] = adapter.device
    adapter._cache.clear()
    return result
