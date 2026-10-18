"""Reporting preserves incomplete seeds and authored stress-test evidence."""
import hashlib
import json

from cascade_guard.cheap_report import refresh


def test_report_preserves_missing_seed_raw_results_and_final_manifest(tmp_path):
    root = tmp_path / "results/cheap-guards"
    evaluation = root / "evaluation"
    raw = evaluation / "raw64"
    raw.mkdir(parents=True)
    (tmp_path / "reports").mkdir()
    (root / "run.json").write_text(json.dumps({"immutable_sha256": {}, "status": "PARTIAL"}))
    (root / "finalizer.json").write_text('{"status": "REPORTING"}')
    metrics = []
    for seed, complete in ((17, True), (29, False), (43, True)):
        metrics.append({"seed": seed, "arm": "train_selected_combo:original_rules", "complete": complete,
                        "harm_prevented_counterfactual": {"k": 82, "n": 83},
                        "raw_episode_fpr": {"k": 2, "n": 131},
                        "p4_reached_safe93_interruption": {"k": 2, "n": 93},
                        "source_benign_compliant_completion_counterfactual": {"k": 60, "n": 98},
                        "unknown_stop": 0, "brier": None})
    (evaluation / "metrics.json").write_text(json.dumps({"aggregates": metrics}))
    (raw / "metrics.json").write_text(json.dumps({"aggregates": [{"seed": 17, "arm": "R2", "complete": True, "TP": 29, "FP": 0, "unknown_stop": 0}]}))
    (raw / "unsupported.json").write_text(json.dumps([{"seed": 17, "arm": "train_selected_combo:none", "reason": "J checkpoint unavailable"}]))
    refresh(tmp_path)
    page = (tmp_path / "reports/cheap-report.html").read_text()
    assert "82 / — / 82" in page
    assert "Известный raw64 стресс-тест" in page and "<td>29</td>" in page
    assert "J checkpoint unavailable" in page
    manifest = json.loads((root / "report-manifest.json").read_text())
    assert "results/cheap-guards/finalizer.json" not in manifest["sha256"]
    assert manifest["sha256"]["reports/cheap-report.html"] == hashlib.sha256((tmp_path / "reports/cheap-report.html").read_bytes()).hexdigest()
