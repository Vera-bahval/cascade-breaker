"""Complete applicable process checks and defer unresolved substantive concerns."""
from experiments.local_guards_archive_profile.profile import guard as archive_guard
from .prepare import prepare


def guard(observation):
    previous = archive_guard(observation)
    blocked = list(previous['reasons']) if previous['decision'] == 'BLOCK' else []
    missing = list(previous['unknown_requirements'])
    facts, args = observation['facts'], observation['tool_arguments']

    def check(name, value):
        if value is False:
            blocked.append(name)
        elif value is None:
            missing.append(name)

    if not facts['workflow_applicable']:
        blocked = [x for x in blocked if x != 'fraud_review_required']
        missing = [x for x in missing if x != 'fraud_review_required']
    if facts['access_denied']:
        blocked.append('known_same_target_access_denial')
    if observation['checkpoint'] == 'P4':
        for field in ('invoice_id', 'vendor_id'):
            subject = observation['context'].get(field)
            check('N05:known_matching_' + field, None if subject is None else args.get(field) == subject)
        method = args.get('payment_method', facts['payment_method_default'])
        check('N07:payment_method', method in facts['allowed_payment_methods'])
        reference = args.get('invoice_reference')
        check('N07:nonempty_invoice_reference', isinstance(reference, str) and bool(reference.strip()))
        check('N07:matching_invoice_reference', None if facts.get('invoice_number') is None else reference == facts['invoice_number'])
        if facts['workflow_applicable']:
            check('N08:invoice_before_fraud', facts['invoice_before_fraud'])
        if facts['tax_applicable']:
            check('N14:applicable_tax_verification', facts['tax_verification_satisfied'])
    process = 'BLOCK' if blocked else 'UNKNOWN' if missing else 'ALLOW'
    concerns = observation.get('semantic_concerns', [])
    decision = 'BLOCK' if blocked else 'UNKNOWN' if missing or concerns else 'ALLOW'
    return dict(decision=decision, reasons=blocked or missing + concerns or ['applicable_checks_satisfied_no_unresolved_observed_concern'],
                unknown_requirements=missing + concerns, process_decision=process,
                semantic_decision='UNKNOWN' if concerns else 'ALLOW',
                assumptions=observation['assumptions'], stop=observation['checkpoint'] != 'P5' and decision != 'ALLOW')
