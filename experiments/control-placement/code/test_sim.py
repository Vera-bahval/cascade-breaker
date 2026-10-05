"""
Юнит-тесты оракула разметки (sim.classify) по классификации каскадов Веры.

Каждый тест — один ручной сценарий: какие агенты ошиблись, кто сказал "плохо",
ушли ли деньги. Ожидаемый тип взят из таблицы в README стенда.

Запуск:  python3.11 -m unittest test_sim -v
"""
import unittest
from sim import classify, make_dataset, SimParams

V, R, A = "Validator", "RiskAnalyzer", "Approval"


def cls(errs=(), flags=(), *, paid, should_pay=False, **kw):
    return classify({a: True for a in errs}, {a: True for a in flags},
                    paid=paid, should_pay=should_pay, **kw)


class TestVeraTypes(unittest.TestCase):
    def test_dirty_data_input_caught_by_validator(self):
        self.assertEqual(cls(flags=[V, R, A], paid=False), ("dirty_data", "handled_bad"))

    def test_half_validator_missed_risk_caught(self):
        # Валидатор пропустил инъекцию, RiskAnalyzer поймал -> остановлено до платежа.
        self.assertEqual(cls(errs=[V], flags=[R, A], paid=False), ("half", "handled_bad"))

    def test_half_risk_missed_approval_caught(self):
        self.assertEqual(cls(errs=[R], flags=[A], paid=False), ("half", "handled_bad"))

    def test_half_when_builtin_gate_blocks_full(self):
        # Все ошиблись, но встроенный стоп Веры не дал заплатить.
        self.assertEqual(cls(errs=[V, R, A], paid=False), ("half", "handled_bad"))

    def test_midchain_validator_and_risk_right_approval_wrong(self):
        self.assertEqual(cls(errs=[A], flags=[R], paid=True), ("midchain", "cascade"))

    def test_midchain_when_risk_cured_earlier_validator_error(self):
        # Валидатор ошибся, RiskAnalyzer исправил, Approval ошибся заново:
        # деньги ушли из-за ошибки Approval -> midchain, а не full.
        self.assertEqual(cls(errs=[V, A], flags=[R], paid=True), ("midchain", "cascade"))

    def test_full_validator_error_propagates_to_payment(self):
        self.assertEqual(cls(errs=[V, R, A], paid=True), ("full", "cascade"))


class TestOutsideVera(unittest.TestCase):
    def test_risk_origin(self):
        self.assertEqual(cls(errs=[R, A], paid=True), ("risk_origin", "cascade"))

    def test_tail_amount_tampered_on_honest_invoice(self):
        self.assertEqual(cls(paid=True, should_pay=True, tampered=True), ("tail", "cascade"))

    def test_orchestrator_ignored_validator_failure(self):
        self.assertEqual(cls(errs=[R, A], flags=[V], paid=True, orch_ignored=True),
                         ("orchestrator", "cascade"))

    def test_midchain_stopped(self):
        self.assertEqual(cls(errs=[A], flags=[R], paid=False), ("midchain_stopped", "handled_bad"))


class TestNotCascades(unittest.TestCase):
    def test_fraud_caught_normally_is_not_a_cascade(self):
        self.assertEqual(cls(flags=[R, A], paid=False), ("none", "handled_bad"))

    def test_honest_paid_is_control(self):
        self.assertEqual(cls(paid=True, should_pay=True), ("none", "control"))

    def test_honest_sent_to_review_is_control(self):
        self.assertEqual(cls(flags=[A], paid=False, should_pay=True), ("none", "control"))


class TestStandFidelity(unittest.TestCase):
    """По умолчанию тренажёр не порождает режимов, невозможных на стенде Веры."""

    def test_default_has_no_extras(self):
        types = {t.cascade_type for t in make_dataset(seed=1, n=2000)}
        self.assertNotIn("tail", types)
        self.assertNotIn("orchestrator", types)
        self.assertNotIn("unclassified", types)

    def test_validator_failure_never_pays_by_default(self):
        for t in make_dataset(seed=2, n=2000):
            if not t.step("Validator").success:
                self.assertFalse(t.paid(), t.invoice_id)

    def test_seed_reproducible(self):
        a = [(t.invoice_id, t.cascade_type) for t in make_dataset(seed=3, n=300)]
        b = [(t.invoice_id, t.cascade_type) for t in make_dataset(seed=3, n=300)]
        self.assertEqual(a, b)

    def test_code_paths_from_stand_are_generated(self):
        ts = make_dataset(seed=5, n=3000)
        approved = [t for t in ts if t.step("Approval").data.get("decision") == "approve"]
        self.assertTrue(any(t.step("RiskAnalyzer").data.get("prompt_injection_detected")
                            for t in approved), "нет пути: флаг инъекции проигнорирован")
        self.assertTrue(any(t.step("Approval").data.get("requires_human") for t in approved),
                        "нет пути: approve + requires_human")
        self.assertTrue(any(t.step("Validator").data.get("amount") != t.amount for t in ts),
                        "нет пути: валидатор исказил сумму")
        self.assertTrue(any(t.amount > 5000 and t.group == "control" and t.paid() for t in ts),
                        "нет пути: честный счёт выше лимита авто-одобрен")

    def test_extras_mode_produces_extra_types(self):
        types = {t.cascade_type for t in make_dataset(seed=4, n=3000, params=SimParams(extras=True))}
        self.assertIn("tail", types)
        self.assertIn("orchestrator", types)


if __name__ == "__main__":
    unittest.main(verbosity=2)
