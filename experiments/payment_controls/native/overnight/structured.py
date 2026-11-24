"""Opt-in output-format contrast for the unmodified native Fraud workflow."""
from contextlib import contextmanager

STRUCTURED_INSTRUCTION = '''
In the complete_task task_summary, retain all native responsibilities and include
four short fields on separate lines: invoice_id, disposition, unresolved, evidence.
Use unknown when a field is not established; do not invent facts or omit material findings.
'''


@contextmanager
def structured_fraud():
    from finbot.agents.specialized.fraud import FraudComplianceAgent
    original = FraudComplianceAgent._get_final_system_prompt
    def prompt(agent):
        return original(agent) + STRUCTURED_INSTRUCTION
    FraudComplianceAgent._get_final_system_prompt = prompt
    try:
        yield
    finally:
        FraudComplianceAgent._get_final_system_prompt = original
