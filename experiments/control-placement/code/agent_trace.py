"""
Framework-agnostic представление прогона мультиагентной цепочки.

Идея: проверки согласованности не должны знать про FinBot/Flask/OpenAI.
Они работают над нормализованным ТРЕЙСОМ — списком шагов агентов. Тот же трейс
можно получить и из синтетического генератора (для measurement), и из живого
FinBot (тонкий адаптер конвертит AgentResult -> Step). Поля Step повторяют
реальный AgentResult из src/services/multi_agent_finbot.py.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Optional

# Порядок цепочки. Индекс = "граница", на которой доступен вывод агента.
AGENTS = ["Validator", "RiskAnalyzer", "Approval", "PaymentProcessor"]

# Номинальная стоимость шага (сек). Валидатор/риск/аппрув — LLM-вызовы (дорого),
# платёж — дешёвая операция. Нужно для оценки latency/overhead и экономии от
# раннего обрыва каскада.
STEP_LATENCY = {
    "Validator": 0.50,
    "RiskAnalyzer": 0.70,
    "Approval": 0.60,
    "PaymentProcessor": 0.05,
}


@dataclass
class Step:
    """Один шаг агента — зеркало AgentResult(success, data, confidence, errors)."""
    agent: str
    success: bool
    confidence: float
    data: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)
    latency_s: float = 0.0


@dataclass
class Trace:
    """Полный прогон одного счёта через цепочку + ground truth (для синтетики)."""
    invoice_id: str
    amount: float                 # истинная сумма счёта
    steps: list = field(default_factory=list)  # list[Step] в порядке цепочки

    # Ground truth известен только для синтетики/размеченных прогонов.
    is_cascade: bool = False      # True = "плохой" платёж, который надо было оборвать
    cascade_type: str = "none"    # none/dirty_data/half/midchain/full
    label_reason: str = ""
    # Популяция прогона (для метрик):
    #   control      — исправный (легитимный) счёт; FPR считаем только здесь;
    #   cascade      — произошёл вредный платёж (is_cascade=True);
    #   handled_bad  — плохой счёт, но система его корректно остановила (не платёж).
    group: str = "control"

    def step(self, agent: str) -> Optional[Step]:
        for s in self.steps:
            if s.agent == agent:
                return s
        return None

    def paid(self) -> bool:
        p = self.step("PaymentProcessor")
        return bool(p and p.data.get("payment_processed"))

    def boundary_index(self, agent: str) -> int:
        return AGENTS.index(agent)
