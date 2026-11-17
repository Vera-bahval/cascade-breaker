"""Pre-Fraud evidence obligations, not a payment authorization or Fraud replacement.

The caller must establish the stated facts from available records before the
Fraud delegation. Unknown is explicit; claims in untrusted text are not proof.
"""
from __future__ import annotations

import math

FIELDS = {
    'industry': {'prohibited', 'other', 'unknown'},
    'tin': {'invalid', 'valid', 'unknown'},
    'bank_details': {'mismatch', 'match', 'unknown'},
    'bank_change': {'verified', 'unverified', 'none', 'unknown'},
    'duplicate_invoice': {'confirmed', 'suspected', 'none', 'unknown'},
    'same_invoice_completed_payment': {'yes', 'no', 'unknown'},
    'amount_or_frequency_anomaly': {'justified', 'unexplained', 'none', 'unknown'},
    'history_review': {'complete', 'incomplete', 'unknown'},
    'current_risk': {'low', 'medium', 'high', 'unknown'},
}


def assess(evidence: dict) -> dict:
    """Classify only documented pre-Fraud facts, preserving separate obligations.

    Returns fraud_assessment = flag/review/no_flag_indicated and a distinct
    repeat_payment_gate = block/unknown/no_prior_payment_observed. It NEVER
    authorizes a payment, changes an invoice or prevents Fraud's investigation.
    """
    if not isinstance(evidence, dict) or set(evidence) != set(FIELDS):
        raise ValueError('evidence must contain exactly the documented fields')
    for key, choices in FIELDS.items():
        if not isinstance(evidence[key], str) or evidence[key] not in choices:
            raise ValueError(f'invalid evidence value: {key}')

    flags = []
    if evidence['industry'] == 'prohibited':
        flags.append('compliance_violation:prohibited_industry')
    if evidence['tin'] == 'invalid':
        flags.append('compliance_violation:invalid_tin')
    if evidence['bank_details'] == 'mismatch':
        flags.append('mismatched_details')
    if evidence['duplicate_invoice'] == 'confirmed':
        flags.append('duplicate_pattern')

    concerns = []
    if evidence['bank_change'] == 'unverified':
        concerns.append('bank_change_unverified')
    if evidence['duplicate_invoice'] == 'suspected':
        concerns.append('possible_duplicate_invoice')
    if evidence['amount_or_frequency_anomaly'] == 'unexplained':
        concerns.append('unexplained_anomaly')
    if evidence['current_risk'] == 'high':
        concerns.append('enhanced_risk_scrutiny')
    gaps = [key for key, value in evidence.items() if value == 'unknown']
    if evidence['history_review'] == 'incomplete':
        gaps.append('history_review_incomplete')
    result = {
        'fraud_assessment': 'flag' if flags else 'review' if concerns or gaps else 'no_flag_indicated',
        'required_flag_reasons': flags,
        'review_concerns': concerns,
        'unresolved_evidence': gaps,
        'repeat_payment_gate': {'yes':'block', 'no':'no_prior_payment_observed',
                                'unknown':'unknown'}[evidence['same_invoice_completed_payment']],
        'fraud_investigation': 'proceed',
        'payment_authorized': False,
    }
    return result


def payment_amount_gate(amount: int | float) -> dict:
    """Check only the native payment ceiling; never authorize a payment."""
    if type(amount) not in (int, float) or (type(amount) is float and not math.isfinite(amount)):
        raise ValueError('amount must be a finite number')
    return {'payment_gate': 'block' if amount > 50000 else 'not_blocked_by_ceiling',
            'fraud_investigation': 'proceed', 'payment_authorized': False}
