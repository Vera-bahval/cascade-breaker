"""Post-hoc presentation keeps populations, incomplete seeds and provenance explicit."""
import hashlib
import json

from cascade_guard.cheap_policy_report import per_group, refresh, seed_values


def sample(seed, policy="A_joint", complete=True):
    result = dict(seed=seed, policy=policy, arm="train_selected_combo:original_rules", complete=complete,
                  unknown_stop=0, pr_auc=.8, brier=.1, log_loss=.3)
    for name, k, n in (("harm_prevented_counterfactual", 78, 83), ("raw_episode_fpr", 2, 131),
                       ("p4_reached_safe93_interruption", 2, 93), ("source_benign_stop", 33, 98),
                       ("source_benign_compliant_completion_counterfactual", 60, 98)):
        result[name] = dict(k=k, n=n, rate=k/n)
    return result


def test_seed_display_does_not_pool_or_fill_missing():
    rows = [sample(17), sample(29, complete=False)]
    assert seed_values(rows, "harm_prevented_counterfactual", count=True) == "78 / — / —"


def test_saved_report_contains_posthoc_raw_missing_and_all_methods(tmp_path):
    root = tmp_path / "results/policy-comparison"
    main = root / "main"
    main.mkdir(parents=True)
    rows = [sample(17), sample(43, "C_lowest")]
    rows.append(dict(sample(17, "B_independent"), arm="<unsafe label>"))
    (main / "metrics.json").write_text(json.dumps({"aggregates": rows}))
    (main / "predictions.jsonl").write_text(json.dumps(dict(seed=17, policy="A_joint", arm=rows[0]["arm"], reconstructed_total_guard_ms=12)) + "\n")
    raw = root / "raw64"
    raw.mkdir()
    (raw / "metrics.json").write_text(json.dumps({"aggregates": [dict(seed=17, policy="C_lowest", arm="R2", TP=29, FP=0, unknown_stop=0)]}))
    (raw / "unsupported.json").write_text(json.dumps([{"reason": "no genuine four-checkpoint sequence"}]))
    review = root / "review"
    review.mkdir()
    (review / "independent-method-review.md").write_text("# Future families\n\nVersion drift and paired safe controls; proposal only.")
    report = refresh(tmp_path)
    content = report.read_text()
    assert "POST-HOC" in content and "не три независимые выборки" in content
    assert "78 / — / —" in content and "— / — / 78" in content
    assert "&lt;unsafe label&gt;" in content and "<unsafe label>" not in content
    assert "Достигшие P4 безопасные STOP /93" in content
    assert "Остановлены исходно честные /98" in content
    assert "no genuine four-checkpoint sequence" in content
    assert "Version drift" in content and "не являются уже выполненным" in content
    assert "text-reference-verified-final: результаты пока отсутствуют" in content
    manifest = json.loads((root / "report-manifest.json").read_text())
    assert manifest["metric_rows"] == 4
    assert manifest["sha256"]["reports/cheap-policy-report.html"] == hashlib.sha256(report.read_bytes()).hexdigest()
    csv = (root / "comparison.csv").read_text()
    assert "harm_prevented_counterfactual_n" in csv and "B_independent" in csv


def test_empty_report_is_explicitly_incomplete(tmp_path):
    content = refresh(tmp_path).read_text()
    assert "main: результаты пока отсутствуют" in content
    assert "Ревью ещё не сохранено" in content


def test_heldout_group_uses_causal_groups_and_strict_timing():
    outcomes = [dict(episode_id="h", group_id="g", strict_harm=True, strict_harm_seq=10),
                dict(episode_id="s", group_id="g", strict_harm=False)]
    records = []
    for arm in ("R1", "catboost:J_seq:original_rules"):
        for episode in ("h", "s"):
            records.append(dict(episode_id=episode, prefix_id=episode, policy="A_joint", seed=17,
                                arm=arm, cut_seq=10 if arm == "R1" else 9, block=arm != "R1", unknown=False))
    rows = per_group(records, outcomes, "main")
    model = next(r for r in rows if r["arm"] != "R1")
    assert model["TP"] == model["additional_TP_beyond_R1"] == 1
    assert model["FP"] == model["additional_FP_beyond_R1"] == 1
    assert model["harm_n"] == model["safe_n"] == 1
