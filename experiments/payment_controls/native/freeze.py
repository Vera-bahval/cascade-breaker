"""Capture offline default FinBot agent definitions; no workflow, MCP connection or LLM call.

Run with: PYTHONPATH=finbot:scenarios finbot/.venv/bin/python experiments/payment_controls/native/freeze.py
Actual runtime prompts and tool schemas must be checked against trace receipts separately.
"""
from __future__ import annotations
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
DEST = Path(__file__).with_name('build_freeze.json')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    from runner.direct_mode import session_for
    from finbot.agents.orchestrator import OrchestratorAgent
    from finbot.agents.specialized.fraud import FraudComplianceAgent
    from finbot.agents.specialized.invoice import InvoiceAgent
    from finbot.agents.specialized.payments import PaymentsAgent
    from finbot.agents.specialized.onboarding import VendorOnboardingAgent
    from finbot.agents.specialized.communication import CommunicationAgent
    from finbot.mcp.servers.taxcalc.server import DEFAULT_CONFIG, invoice_tax
    from finbot.probe import policy

    classes = (OrchestratorAgent, FraudComplianceAgent, InvoiceAgent, PaymentsAgent,
               VendorOnboardingAgent, CommunicationAgent)
    session = session_for('native-freeze-local')
    agents = {}
    for cls in classes:
        # Avoid agent construction (LLM client and event/guard services); these methods
        # use only default config and the synthetic session until MCP is connected.
        agent = object.__new__(cls)
        agent.session_context = session
        agent.agent_config = agent._load_config()
        agent._mcp_provider = None
        prompt = agent._get_final_system_prompt()
        # The generated timestamp is not fixed across runs or representative of runtime.
        prompt = re.sub(r'(Current Date and Time: )[^\n]+', r'\1<RUNTIME_UTC>', prompt)
        agents[cls.__name__] = {'default_config': agent.agent_config,
                                'synthetic_final_system_prompt': prompt,
                                'unconnected_tool_definitions': agent._get_final_tool_definitions()}
    tracked = subprocess.check_output(['git','ls-files','-z','finbot'], cwd=ROOT).split(b'\0')
    paths = [ROOT / x.decode() for x in tracked if x]
    paths += [ROOT / x for x in ('scenarios/runner/direct_mode.py',
        'finbot/finbot/probe/guards/workflow.py', 'experiments/payment_controls/study/enforce.py',
        'experiments/payment_controls/native/verifier.py', 'experiments/payment_controls/native/freeze.py')]
    paths = sorted(set(p for p in paths if p.is_file()))
    versions = {}
    for name in ('fastmcp','pydantic','sqlalchemy','httpx','openai'):
        try: versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: versions[name] = None
    status = subprocess.check_output(['git','status','--porcelain=v1','--untracked-files=all'], cwd=ROOT, text=True).splitlines()
    result = {
        'schema': 'native-freeze-v1',
        'scope': 'offline default static extraction, synthetic namespace; no MCP servers or LLM calls',
        'git_head': subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
        'git_status_porcelain': status,
        'file_sha256': {str(p.relative_to(ROOT)): sha(p) for p in paths},
        'python': platform.python_version(), 'packages': versions,
        'synthetic_session': {'namespace': session.namespace, 'user_id': session.user_id,
                              'is_temporary': session.is_temporary},
        'static_defaults': {'agents': agents, 'taxcalc': DEFAULT_CONFIG,
                            'policy_constants': {k:v for k,v in vars(policy).items() if k.isupper() and isinstance(v,(str,int,float,bool))},
                            'example_480_services_default': invoice_tax(480,'','services',DEFAULT_CONFIG)},
        'observed_runtime': {'status':'not captured', 'required':'Use each runtime LLM trace messages and tool_defs by tools_sha; MCP config and overrides are namespace-dependent.'},
        'snapshot_sources': ['finbot/finbot/probe/guards/workflow.py:workflow_snapshot',
                             'scenarios/runner/direct_mode.py:snapshot',
                             'experiments/payment_controls/native/verifier.py:setup_guard.state'],
    }
    assert all(x['unconnected_tool_definitions'] for x in agents.values())
    assert result['static_defaults']['example_480_services_default']['total_amount'] == 480
    DEST.write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)+'\n')
    print(f'Wrote {DEST.relative_to(ROOT)}: {len(agents)} agents, {len(paths)} file hashes; runtime not captured')


if __name__ == '__main__':
    main()
