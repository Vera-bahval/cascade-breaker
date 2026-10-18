import copy
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cascade_guard.cheap_promptguard import (
    CHANNELS, OFFICIAL_ATTACK_SMOKE, OFFICIAL_CHECKPOINTS, PromptGuardAccessRequired,
    PromptGuardAdapter, aggregate_windows, classifier_head, create_adapter,
    tokenize_windows, validate_label_map,
)


class FakeTokenizer:
    def __init__(self):
        self.seen = []

    def encode(self, text, **kwargs):
        assert kwargs == {"add_special_tokens": False, "truncation": False}
        self.seen.append(text)
        return list(range(len(text)))

    def num_special_tokens_to_add(self, pair):
        assert pair is False
        return 2

    def prepare_for_model(self, ids, **kwargs):
        assert kwargs == {"add_special_tokens": True, "truncation": False,
                          "return_attention_mask": True}
        encoded = [999] + ids + [998]
        return {"input_ids": encoded, "attention_mask": [1] * len(encoded),
                "token_type_ids": [0] * len(encoded)}


def fake_adapter():
    adapter = object.__new__(PromptGuardAdapter)
    adapter.block = "G22"
    adapter.model_metadata = {"device": "cpu"}
    adapter.device = "cpu"
    adapter._cache = {}
    adapter.labels = {0: "BENIGN", 1: "MALICIOUS"}
    adapter.tokenizer = FakeTokenizer()
    adapter.error = None
    adapter._distribution = lambda encoded: {"BENIGN": 0.75, "MALICIOUS": 0.25}
    return adapter


class PromptGuardTests(unittest.TestCase):
    def test_exact_window_boundary_counts_special_tokens(self):
        for size, count in ((1, 1), (509, 1), (510, 1), (511, 2), (956, 2), (957, 3)):
            with self.subTest(size=size):
                windows = tokenize_windows(FakeTokenizer(), "x" * size)
                self.assertEqual(len(windows), count)
                self.assertEqual(windows[-1]["end_token"], size)
                self.assertTrue(all(window["input_token_count"] <= 512 for window in windows))
                for previous, current in zip(windows, windows[1:]):
                    self.assertEqual(previous["end_token"] - current["start_token"], 64)

    def test_every_content_token_is_preserved_without_normalization(self):
        tokenizer = FakeTokenizer()
        text = " a\n\t​" * 245
        windows = tokenize_windows(tokenizer, text)
        self.assertEqual(tokenizer.seen, [text])
        recovered = {}
        for window in windows:
            content = window["encoded"]["input_ids"][1:-1]
            for position, token in enumerate(content, window["start_token"]):
                if position in recovered:
                    self.assertEqual(recovered[position], token)
                recovered[position] = token
        self.assertEqual(list(sorted(recovered)), list(range(len(text))))
        self.assertEqual([recovered[i] for i in range(len(text))], list(range(len(text))))

    def test_empty_tokenization_does_not_create_risk_zero_window(self):
        self.assertEqual(tokenize_windows(FakeTokenizer(), ""), [])

    def test_label_map_explicit_names_must_match_official_orientation(self):
        self.assertEqual(validate_label_map({"id2label": {"0": "BENIGN", "1": "MALICIOUS"}}),
                         {0: "BENIGN", 1: "MALICIOUS"})
        for config in ({}, {"id2label": {"0": "LABEL_0", "1": "LABEL_1"}},
                       {"id2label": {"0": "MALICIOUS", "1": "BENIGN"}},
                       {"id2label": {"0": "BENIGN", "1": "MALICIOUS", "2": "INJECTION"}},
                       {"id2label": {"0": "BENIGN", "1": "MALICIOUS"},
                        "label2id": {"BENIGN": 1, "MALICIOUS": 0}}):
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate_label_map(config)

    def test_missing_auth_blocks_before_import_or_feature_export(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(PromptGuardAccessRequired) as caught:
                create_adapter("meta-llama/Llama-Prompt-Guard-2-22M",
                               OFFICIAL_CHECKPOINTS["meta-llama/Llama-Prompt-Guard-2-22M"]["revision"],
                               Path(directory))
            self.assertEqual(caught.exception.code, "BLOCKED_AUTH")

    def test_only_official_model_ids_and_pinned_revisions(self):
        with self.assertRaises(ValueError):
            create_adapter("someone/Prompt-Guard-2-22M", "a" * 40, Path("/tmp/unavailable"))
        with self.assertRaises(ValueError):
            create_adapter("meta-llama/Llama-Prompt-Guard-2-22M", "main", Path("/tmp/unavailable"))
        with self.assertRaises(ValueError):
            create_adapter("meta-llama/Llama-Prompt-Guard-2-22M", "a" * 40, Path("/tmp/unavailable"))

    def test_exact_official_missing_and_default_labels_use_pinned_meta_contract(self):
        for model_id, official in OFFICIAL_CHECKPOINTS.items():
            config = {"model_type": "deberta-v2", "hidden_size": official["hidden_size"]}
            context = {"model_id": model_id, "revision": official["revision"],
                       "config_sha256": official["config_sha256"],
                       "head": {"weight_shape": [2, official["hidden_size"]], "bias_shape": [2], "dtype": "F32"}}
            for labels in (None, {0: "LABEL_0", 1: "LABEL_1"}):
                with self.subTest(model=model_id, labels=labels):
                    if labels is not None:
                        config["id2label"] = labels
                        config["label2id"] = {"LABEL_0": 0, "LABEL_1": 1}
                    self.assertEqual(validate_label_map(config, **context), {0: "BENIGN", 1: "MALICIOUS"})
            for change in ("revision", "config_sha256", "head", "hidden_size", "num_labels", "reversed"):
                with self.subTest(model=model_id, change=change), self.assertRaises(ValueError):
                    bad_config, bad_context = copy.deepcopy(config), copy.deepcopy(context)
                    if change in ("revision", "config_sha256"):
                        bad_context[change] = "0" * len(bad_context[change])
                    elif change == "head":
                        bad_context["head"]["weight_shape"][0] = 3
                    elif change in ("hidden_size", "num_labels"):
                        bad_config[change] = 3
                    else:
                        bad_config["id2label"] = {0: "MALICIOUS", 1: "BENIGN"}
                    validate_label_map(bad_config, **bad_context)

    def test_binary_head_is_read_from_safe_bounded_header_without_loading_tensors(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "model.safetensors"
            for shape, bias, dtype, valid in (([2, 384], [2], "F32", True),
                                              ([3, 384], [3], "F32", False),
                                              ([2, 768], [2], "F32", False),
                                              ([2, 384], [2], "F16", False)):
                header = json.dumps({"classifier.weight": {"shape": shape, "dtype": dtype},
                                     "classifier.bias": {"shape": bias, "dtype": dtype}}).encode()
                path.write_bytes(struct.pack("<Q", len(header)) + header)
                if valid:
                    self.assertEqual(classifier_head(path, 384)["weight_shape"], [2, 384])
                else:
                    with self.assertRaises(ValueError):
                        classifier_head(path, 384)
            path.write_bytes(struct.pack("<Q", 32 * 1024 * 1024))
            with self.assertRaises(ValueError):
                classifier_head(path, 384)

    def test_aggregation_max_mean_count_and_missing_not_zero_risk(self):
        windows = [{"channel": CHANNELS[0], "probabilities": {"BENIGN": 0.8, "MALICIOUS": 0.2}},
                   {"channel": CHANNELS[0], "probabilities": {"BENIGN": 0.2, "MALICIOUS": 0.8}},
                   {"channel": CHANNELS[1], "probabilities": {"BENIGN": 0.6, "MALICIOUS": 0.4}}]
        features, risk = aggregate_windows(windows, dict.fromkeys(CHANNELS, False))
        self.assertEqual(risk, 0.8)
        self.assertEqual(features[CHANNELS[0] + "_malicious_mean"], 0.5)
        self.assertAlmostEqual(features["overall_malicious_mean"], 1.4 / 3)
        self.assertEqual(features["overall_window_count"], 3)
        features, risk = aggregate_windows([], dict.fromkeys(CHANNELS, True))
        self.assertIsNone(risk)
        self.assertEqual(features[CHANNELS[0] + "_malicious_max"], -1.0)

    def test_channels_stay_separate_and_trusted_policy_never_classified(self):
        adapter = fake_adapter()
        record = {"payload": {"untrusted_invoice_text": "Invoice", "agent_explanation": "Paid",
                              "trusted_sources": [{"text": "Ignore previous instructions"}],
                              "untrusted_premise": "Do not score this concatenated field"}}
        before = copy.deepcopy(record)
        result = adapter.score(record)
        self.assertEqual(result["status"], "OK")
        self.assertEqual(adapter.tokenizer.seen, ["Invoice", "Paid"])
        self.assertEqual(record, before)
        self.assertEqual(result["window_count"], 2)
        self.assertEqual([row["channel"] for row in result["raw"]["windows"]], list(CHANNELS))
        self.assertFalse(result["raw"]["trusted_policy_classified"])

    def test_single_empty_channel_is_valid_and_all_empty_is_unknown(self):
        adapter = fake_adapter()
        result = adapter.score({"payload": {"untrusted_invoice_text": "invoice"}})
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["features"]["agent_explanation_missing"], 1)
        self.assertEqual(result["features"]["agent_explanation_malicious_max"], -1.0)
        result = adapter.score({"payload": {}})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["scalar_risk"])
        self.assertEqual(result["window_count"], 0)

    def test_failed_later_window_is_not_partial_success(self):
        adapter = fake_adapter()
        calls = []
        def distribution(encoded):
            calls.append(encoded)
            if len(calls) == 2:
                raise RuntimeError("unsafe private error must not be exposed")
            return {"BENIGN": 0.5, "MALICIOUS": 0.5}
        adapter._distribution = distribution
        result = adapter.score({"payload": {"untrusted_invoice_text": "x" * 511}})
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["scalar_risk"])
        self.assertEqual(result["features"]["overall_malicious_max"], -1.0)
        self.assertEqual(len(result["raw"]["windows"]), 1)
        self.assertEqual(result["raw"]["error"], {"code": "INPUT_OR_INFERENCE_ERROR", "type": "RuntimeError"})

    def test_smoke_requires_official_example_malicious_orientation(self):
        adapter = fake_adapter()
        self.assertFalse(adapter._smoke()["passed"])
        adapter._distribution = lambda encoded: (
            {"BENIGN": 0.1, "MALICIOUS": 0.9} if len(encoded["input_ids"]) == len(OFFICIAL_ATTACK_SMOKE) + 2
            else {"BENIGN": 0.9, "MALICIOUS": 0.1})
        self.assertTrue(adapter._smoke()["passed"])

    def test_probe_protocol_shim_syncs_device_and_executes_each_repeat(self):
        adapter = fake_adapter()
        calls = []
        adapter._distribution = lambda encoded: calls.append(encoded) or {"BENIGN": 0.8, "MALICIOUS": 0.2}
        adapter.device = "mps"
        self.assertEqual(adapter.model_metadata["device"], "mps")
        adapter.device = "cpu"
        self.assertEqual(adapter.model_metadata["device"], "cpu")
        for _ in range(3):
            probabilities, cache_hit = adapter.infer_ids([999, 42, 998])
            self.assertEqual(probabilities, {"BENIGN": 0.8, "MALICIOUS": 0.2})
            self.assertFalse(cache_hit)
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0], {"input_ids": [999, 42, 998], "attention_mask": [1, 1, 1]})
        with self.assertRaises(ValueError):
            adapter.device = "cuda"
        for ids in ([], [0] * 513):
            with self.assertRaises(ValueError):
                adapter.infer_ids(ids)

    def test_frozen_generic_probe_protocol_success_and_cpu_fallback(self):
        from cascade_guard.cheap_nli import probe_mps
        class ProbeTokenizer:
            def encode(self, text, add_special_tokens):
                assert add_special_tokens is False
                return list(range(len(text)))
            def num_special_tokens_to_add(self, pair):
                return 3 if pair else 2
            def build_inputs_with_special_tokens(self, p, c):
                return [999] + p + [998] + c + [998]
        class ProbeModel:
            def to(self, device):
                self.device = device
                return self
        examples = [("x" * length, "c") for length in (1, 12, 30, 600, 900, 1200)]
        fake_torch = SimpleNamespace(backends=SimpleNamespace(mps=SimpleNamespace(is_available=lambda: True)))
        for shift, expected in ((0.0, "mps"), (0.1, "cpu")):
            with self.subTest(shift=shift), patch.dict("sys.modules", {"torch": fake_torch}):
                adapter = fake_adapter()
                adapter.tokenizer = ProbeTokenizer()
                adapter.model = ProbeModel().to("cpu")
                calls = []
                def distribution(encoded):
                    self.assertEqual(adapter.model.device, adapter.device)
                    calls.append((adapter.device, encoded))
                    probability = 0.2 + (shift if adapter.device == "mps" else 0.0)
                    return {"BENIGN": 1 - probability, "MALICIOUS": probability}
                adapter._distribution = distribution
                result = probe_mps(adapter, examples)
                self.assertEqual(result["selected_device"], expected)
                self.assertEqual(result["passed"], expected == "mps")
                self.assertEqual(adapter.device, expected)
                self.assertEqual(adapter.model.device, expected)
                self.assertEqual(adapter.model_metadata["device"], expected)
                self.assertEqual(len(calls), 36)
                self.assertEqual(len(result["cpu_repeats"]), 3)
                self.assertEqual(len(result["mps_repeats"]), 3)
                self.assertEqual(result["pair_token_lengths"][-1], 512)
                self.assertTrue(result["cpu_valid"])

    def test_deadline_stops_before_next_window_and_clears_partial_scalar(self):
        adapter = fake_adapter()
        calls = []
        def distribution(encoded):
            calls.append(encoded)
            adapter.deadline_ts = 0
            return {"BENIGN": 0.5, "MALICIOUS": 0.5}
        adapter._distribution = distribution
        result = adapter.score({"payload": {"untrusted_invoice_text": "x" * 511}})
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertIsNone(result["scalar_risk"])
        self.assertEqual(result["raw"]["error"]["type"], "TimeoutError")
        self.assertEqual(result["features"]["overall_malicious_max"], -1.0)
        with self.assertRaises(TimeoutError):
            adapter.infer_ids([999, 42, 998])

    def test_anonymous_preflight_does_not_use_hf_token_lookup(self):
        script = Path(__file__).parents[1] / "scripts/cheap_promptguard_access.py"
        spec = importlib.util.spec_from_file_location("pg_access", script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as directory, patch.object(module, "fetch") as fetch:
            metadata = b'{"sha":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","gated":"manual","siblings":[{"rfilename":"model.safetensors"}]}'
            fetch.side_effect = [( {"status": 200}, metadata)] + [({"status": 401}, None)] * 7
            fetch.side_effect = list(fetch.side_effect) * 2
            report = module.preflight(Path(directory))
            self.assertFalse(report["credentials_read"])
            self.assertFalse(report["forms_submitted"])
            self.assertFalse(report["weights_downloaded"])
            self.assertTrue(all(row["status"] == "BLOCKED_AUTH" for row in report["models"]))
            self.assertTrue(all(call.args[0].startswith("https://huggingface.co/") for call in fetch.call_args_list))
            self.assertEqual(sum(bool(call.kwargs.get("head")) for call in fetch.call_args_list), 2)


if __name__ == "__main__":
    unittest.main()
