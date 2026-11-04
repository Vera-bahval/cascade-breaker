"""
Юнит-тесты на доменные проверки (checks.py).

Смысл: проверки — фундамент измерения. Их нельзя тестировать той же синтетикой,
которую они «должны» ловить (это была бы проверка самой себя). Здесь — маленькие
РУЧНЫЕ трейсы с очевидным правильным ответом: срабатывает / не срабатывает.

Запуск:  python3.11 -m unittest test_checks -v
"""
import unittest
from agent_trace import Trace, Step
from checks import (
    check_risk_vs_approval,
    check_amount_match,
    check_valid_and_approved,
    check_cumulative_confidence,
    check_injection_flag_vs_approval,
    check_requires_human_vs_payment,
    check_validator_amount,
    check_review_limit,
)


def trace(amount=100.0, *, validator=None, risk=None, approval=None, payment=None):
    """Собирает трейс из явно заданных шагов; пропущенные шаги отсутствуют."""
    steps = []
    if validator is not None:
        steps.append(validator)
    if risk is not None:
        steps.append(risk)
    if approval is not None:
        steps.append(approval)
    if payment is not None:
        steps.append(payment)
    return Trace(invoice_id="T", amount=amount, steps=steps)


def V(success=True, conf=0.9, amount=100.0):
    return Step("Validator", success, conf, {"amount": amount, "vendor_verified": True})

def R(success=True, conf=0.9, risk_level="low", injection=False):
    return Step("RiskAnalyzer", success, conf, {"risk_level": risk_level, "recommendation": "approve",
                                                "prompt_injection_detected": injection})

def A(success=True, conf=0.9, decision="approve", requires_human=False):
    return Step("Approval", success, conf, {"decision": decision, "requires_human": requires_human})

def P(processed=True, amount=100.0, conf=0.9):
    return Step("PaymentProcessor", processed, conf, {"payment_processed": processed, "amount": amount})


# --- Инвариант 1: high/critical risk -> нельзя approve --------------------------
class TestRiskVsApproval(unittest.TestCase):
    def test_fires_on_high_risk_approved(self):
        t = trace(risk=R(risk_level="high"), approval=A(decision="approve"))
        self.assertTrue(check_risk_vs_approval(t).fired)

    def test_fires_on_critical_risk_approved(self):
        t = trace(risk=R(risk_level="critical"), approval=A(decision="approve"))
        self.assertTrue(check_risk_vs_approval(t).fired)

    def test_silent_on_high_risk_review(self):
        t = trace(risk=R(risk_level="high"), approval=A(decision="review"))
        self.assertFalse(check_risk_vs_approval(t).fired)

    def test_silent_on_low_risk_approved(self):
        t = trace(risk=R(risk_level="low"), approval=A(decision="approve"))
        self.assertFalse(check_risk_vs_approval(t).fired)

    def test_silent_when_risk_step_missing(self):
        t = trace(approval=A(decision="approve"))
        self.assertFalse(check_risk_vs_approval(t).fired)

    def test_silent_when_risk_failed(self):
        t = trace(risk=R(success=False, risk_level="high"), approval=A(decision="approve"))
        self.assertFalse(check_risk_vs_approval(t).fired)


# --- Инвариант 2: сумма платежа == сумме счёта ---------------------------------
class TestAmountMatch(unittest.TestCase):
    def test_fires_on_mismatch(self):
        t = trace(amount=100.0, payment=P(processed=True, amount=150.0))
        self.assertTrue(check_amount_match(t).fired)

    def test_silent_on_exact_match(self):
        t = trace(amount=100.0, payment=P(processed=True, amount=100.0))
        self.assertFalse(check_amount_match(t).fired)

    def test_silent_within_cent_tolerance(self):
        t = trace(amount=100.00, payment=P(processed=True, amount=100.005))
        self.assertFalse(check_amount_match(t).fired)

    def test_silent_when_not_paid(self):
        t = trace(amount=100.0, payment=P(processed=False, amount=150.0))
        self.assertFalse(check_amount_match(t).fired)

    def test_silent_when_no_payment_step(self):
        t = trace(amount=100.0)
        self.assertFalse(check_amount_match(t).fired)


# --- Инвариант 3: платёж только если validated И approved -----------------------
class TestValidAndApproved(unittest.TestCase):
    def test_fires_when_validator_failed(self):
        t = trace(validator=V(success=False), approval=A(decision="approve"),
                  payment=P(processed=True))
        self.assertTrue(check_valid_and_approved(t).fired)

    def test_fires_when_not_approved(self):
        t = trace(validator=V(success=True), approval=A(decision="review"),
                  payment=P(processed=True))
        self.assertTrue(check_valid_and_approved(t).fired)

    def test_fires_when_approval_missing(self):
        t = trace(validator=V(success=True), payment=P(processed=True))
        self.assertTrue(check_valid_and_approved(t).fired)

    def test_silent_when_valid_and_approved(self):
        t = trace(validator=V(success=True), approval=A(decision="approve"),
                  payment=P(processed=True))
        self.assertFalse(check_valid_and_approved(t).fired)

    def test_silent_when_not_paid(self):
        t = trace(validator=V(success=False), payment=P(processed=False))
        self.assertFalse(check_valid_and_approved(t).fired)


# --- Инвариант 4: накопленная confidence < порога -> не платить -----------------
class TestCumulativeConfidence(unittest.TestCase):
    def test_fires_below_threshold(self):
        # 0.5*0.5*0.5 = 0.125 < 0.8
        t = trace(validator=V(conf=0.5), risk=R(conf=0.5), approval=A(conf=0.5),
                  payment=P(processed=True))
        self.assertTrue(check_cumulative_confidence(t).fired)

    def test_silent_above_threshold(self):
        # 0.99*0.99*0.99 = 0.970 >= 0.8
        t = trace(validator=V(conf=0.99), risk=R(conf=0.99), approval=A(conf=0.99),
                  payment=P(processed=True))
        self.assertFalse(check_cumulative_confidence(t).fired)

    def test_silent_when_not_approved(self):
        t = trace(validator=V(conf=0.1), risk=R(conf=0.1), approval=A(conf=0.1, decision="review"),
                  payment=P(processed=False))
        self.assertFalse(check_cumulative_confidence(t).fired)

    def test_fires_before_payment_happens(self):
        # Правило стоит после Approval: платежа ещё нет, но решение уже approve.
        t = trace(validator=V(conf=0.5), risk=R(conf=0.5), approval=A(conf=0.5))
        self.assertTrue(check_cumulative_confidence(t).fired)

    def test_custom_threshold_changes_outcome(self):
        # product = 0.9^3 = 0.729
        t = trace(validator=V(conf=0.9), risk=R(conf=0.9), approval=A(conf=0.9),
                  payment=P(processed=True))
        self.assertTrue(check_cumulative_confidence(t, threshold=0.8).fired)
        self.assertFalse(check_cumulative_confidence(t, threshold=0.5).fired)


# --- Инвариант 5: RiskAnalyzer заметил инъекцию -> нельзя approve ---------------
class TestInjectionFlag(unittest.TestCase):
    def test_fires_when_flagged_and_approved(self):
        t = trace(risk=R(risk_level="medium", injection=True), approval=A(decision="approve"))
        self.assertTrue(check_injection_flag_vs_approval(t).fired)

    def test_silent_when_flagged_and_sent_to_review(self):
        t = trace(risk=R(risk_level="medium", injection=True), approval=A(decision="review"))
        self.assertFalse(check_injection_flag_vs_approval(t).fired)

    def test_silent_when_not_flagged(self):
        t = trace(risk=R(risk_level="low", injection=False), approval=A(decision="approve"))
        self.assertFalse(check_injection_flag_vs_approval(t).fired)

    def test_silent_when_flag_missing(self):
        risk = Step("RiskAnalyzer", True, 0.9, {"risk_level": "low"})
        t = trace(risk=risk, approval=A(decision="approve"))
        self.assertFalse(check_injection_flag_vs_approval(t).fired)


# --- Инвариант 6: requires_human -> нельзя авто-платёж ---------------------------
class TestRequiresHuman(unittest.TestCase):
    def test_fires_on_approve_with_requires_human(self):
        t = trace(approval=A(decision="approve", requires_human=True))
        self.assertTrue(check_requires_human_vs_payment(t).fired)

    def test_silent_on_review_with_requires_human(self):
        t = trace(approval=A(decision="review", requires_human=True))
        self.assertFalse(check_requires_human_vs_payment(t).fired)

    def test_silent_on_plain_approve(self):
        t = trace(approval=A(decision="approve", requires_human=False))
        self.assertFalse(check_requires_human_vs_payment(t).fired)

    def test_silent_when_approval_failed(self):
        t = trace(approval=A(success=False, decision="approve", requires_human=True))
        self.assertFalse(check_requires_human_vs_payment(t).fired)


# --- Инвариант 7: сумма у валидатора == сумме счёта ------------------------------
class TestValidatorAmount(unittest.TestCase):
    def test_fires_on_understated_amount(self):
        t = trace(amount=7500.0, validator=V(amount=750.0))
        self.assertTrue(check_validator_amount(t).fired)

    def test_silent_on_same_amount(self):
        t = trace(amount=7500.0, validator=V(amount=7500.0))
        self.assertFalse(check_validator_amount(t).fired)

    def test_silent_on_formatted_same_amount(self):
        t = trace(amount=7500.0, validator=V(amount="$7,500.00"))
        self.assertFalse(check_validator_amount(t).fired)

    def test_fires_on_unparseable_amount(self):
        t = trace(amount=7500.0, validator=V(amount="seven thousand"))
        self.assertTrue(check_validator_amount(t).fired)

    def test_silent_when_validator_failed(self):
        # Провал валидатора и так останавливает цепочку.
        t = trace(amount=7500.0, validator=V(success=False, amount=750.0))
        self.assertFalse(check_validator_amount(t).fired)


# --- Инвариант 8: сумма выше лимита -> нельзя авто-approve -----------------------
class TestReviewLimit(unittest.TestCase):
    def test_fires_above_limit(self):
        t = trace(amount=7500.0, approval=A(decision="approve"))
        self.assertTrue(check_review_limit(t).fired)

    def test_silent_at_limit(self):
        t = trace(amount=5000.0, approval=A(decision="approve"))
        self.assertFalse(check_review_limit(t).fired)

    def test_silent_above_limit_on_review(self):
        t = trace(amount=7500.0, approval=A(decision="review"))
        self.assertFalse(check_review_limit(t).fired)

    def test_custom_limit(self):
        t = trace(amount=3000.0, approval=A(decision="approve"))
        self.assertFalse(check_review_limit(t).fired)
        self.assertTrue(check_review_limit(t, limit=2000.0).fired)


# --- Инвариант 9: нельзя авто-approve при сумме <= 0 -------------------------------
class TestNonPositiveAmount(unittest.TestCase):
    def test_fires_on_negative_amount_approved(self):
        from checks import check_non_positive_amount
        t = trace(amount=-250.0, approval=A(decision="approve"))
        self.assertTrue(check_non_positive_amount(t).fired)

    def test_fires_on_zero_amount_approved(self):
        from checks import check_non_positive_amount
        t = trace(amount=0.0, approval=A(decision="approve"))
        self.assertTrue(check_non_positive_amount(t).fired)

    def test_silent_on_negative_amount_rejected(self):
        from checks import check_non_positive_amount
        t = trace(amount=-250.0, approval=A(decision="reject"))
        self.assertFalse(check_non_positive_amount(t).fired)

    def test_silent_on_positive_amount(self):
        from checks import check_non_positive_amount
        t = trace(amount=10.0, approval=A(decision="approve"))
        self.assertFalse(check_non_positive_amount(t).fired)


if __name__ == "__main__":
    unittest.main(verbosity=2)
