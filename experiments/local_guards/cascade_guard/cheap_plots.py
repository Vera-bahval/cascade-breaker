"""Static pilot figures; seed ranges are descriptive, not confidence intervals."""
from __future__ import annotations
import argparse
import json
from pathlib import Path


def render(base: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    root = base / "results/cheap-guards"
    metrics = json.loads((root / "evaluation/metrics.json").read_text())["aggregates"]
    matched = root / "matched-reference/metrics.json"
    if matched.exists():
        metrics += [dict(r, arm="matched_4b") for r in json.loads(matched.read_text())["aggregates"] if r["arm"] == "catboost:train_selected_format:original_rules"]
    arms = [("R1", "Исходные rules"), ("R2", "Rules v2"),
            ("catboost:J_cur:original_rules", "Jev: текущие 4"),
            ("catboost:J_seq:original_rules", "Jev: прямые 16"),
            ("catboost:J_agg:original_rules", "Jev: агрегаты"),
            ("catboost:J_dynamic:original_rules", "Jev: динамика"),
            ("catboost:J_prior:original_rules", "Jev: до P4"),
            ("catboost:G22:original_rules", "Prompt Guard 22M"),
            ("catboost:G86:original_rules", "Prompt Guard 86M"),
            ("catboost:N:original_rules", "NLI"),
            ("catboost:M:original_rules", "MiniCheck"),
            ("train_selected_combo:original_rules", "Комбинация: выбор внутри обучения"),
            ("matched_4b", "4B + CatBoost: тот же протокол")]
    fig, ax = plt.subplots(figsize=(11, 6.5))
    for i, (arm, label) in enumerate(arms):
        rows = [r for r in metrics if r["arm"] == arm and r.get("complete")]
        if len(rows) != 3:
            continue
        x = [r["raw_episode_fpr"]["k"] for r in rows]
        y = [r["harm_prevented_counterfactual"]["k"] for r in rows]
        mx, my = sum(x) / 3, sum(y) / 3
        ax.errorbar(mx, my, xerr=[[mx-min(x)], [max(x)-mx]], yerr=[[my-min(y)], [max(y)-my]],
                    fmt=("o", "s", "^", "D", "P", "v")[i % 6], capsize=3, label=label, alpha=.85)
    ax.set(xlabel="Ложные остановки безопасных продолжений, из 131",
           ylabel="Остановленные опасные продолжения, из 83",
           title="Основная серия: совместная калибровка с rules")
    ax.grid(alpha=.2); ax.legend(fontsize=8, loc="best")
    fig.text(.02, .01, "Точки — среднее seeds 17/29/43; отрезки — min–max тех же эпизодов, не доверительные интервалы.", fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, 1)); fig.savefig(root / "quality-comparison.png", dpi=160); plt.close(fig)
    resources = json.loads((root / "evaluation/manifest.json").read_text())["resources_by_block"]
    names, p50, p95, colors = [], [], [], []
    for block in ("J_cur", "J_prior", "J_seq", "G22", "G86", "N", "M"):
        value = resources.get(block, {}).get("inference_cost_ms")
        if value is not None:
            names.append(block); p50.append(value["p50"] / 1000); p95.append(value["p95"] / 1000)
            colors.append("#d99032" if block.startswith("J_") else "#277e99")
    previous_manifest = base / "results/night-4b/evaluation/manifest.json"
    if previous_manifest.exists():
        old = json.loads(previous_manifest.read_text()).get("resources_by_format", {})
        for block in ("plus_rationale", "compact_policy_facts"):
            value = old.get(block, {}).get("total_ms")
            if value:
                names.append("4B: " + ("прежний" if block == "plus_rationale" else "факты")); p50.append(value["p50"] / 1000); p95.append(value["p95"] / 1000); colors.append("#8898a4")
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(names, p50, color=colors, label="p50")
    ax.scatter(names, p95, marker="_", s=220, color="#172b38", label="p95")
    ax.set_yscale("log")
    ax.set(ylabel="Полное извлечение признаков, секунды (log)", title="Цена признаков до CatBoost и правил")
    ax.grid(axis="y", alpha=.2); ax.legend()
    fig.text(.02, .01, "Оранжевый: реконструкция Jev. Синий: новый замер всех окон. Серый: прежний 4B. Холодная загрузка отдельно.", fontsize=8)
    fig.tight_layout(rect=(0, .04, 1, 1)); fig.savefig(root / "feature-latency.png", dpi=160); plt.close(fig)
    return {"figures": ["quality-comparison.png", "feature-latency.png"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path(__file__).resolve().parents[1])
    print(json.dumps(render(parser.parse_args().base)))
