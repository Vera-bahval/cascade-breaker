"""One opt-in isolated live run. This command spends provider funds; tests do not."""
import argparse
import asyncio
import json
import os
from contextlib import nullcontext
from pathlib import Path

from .route import ARMS, install, notification_evidence
from experiments.payment_controls.live_smoke import ROOT, run


async def main(args):
    import experiments.payment_controls.study.live as study_live
    original = study_live.execute
    if args.structured and args.arm != 'overnight-off-v1':
        raise ValueError('structured contrast is only available for the OFF arm')
    fixture_path = Path(args.fixtures).resolve(strict=True)
    os.environ['FINBOT_NATIVE_FIXTURES'] = str(fixture_path)
    os.environ['FINBOT_STUDY_PHASE'] = 'development'
    os.environ['FINBOT_STUDY_VERSION'] = 'overnight-route-v1'
    case_id = '-'.join((args.channel, args.arm, args.case, 'structured-v1' if args.structured else 'overnight-route-v1'))
    legacy = ROOT.parents[1]/'deepseek-flash-control-placement/experiments/control-placement/deepseek_flash'

    async def execute(study, dest, sdk):
        from experiments.payment_controls.native import verifier
        original_setup = verifier.setup_guard
        verifier.setup_guard = lambda *a, **k: nullcontext()
        try:
            from .structured import structured_fraud
            with (structured_fraud() if args.structured else nullcontext()), install(args.arm, dest/'route-decisions.jsonl', packet_path=dest/'route-packets.jsonl',
                         owner_prefix=case_id, provider='jev' if args.arm in ('overnight-model-v1','overnight-hybrid-v1') else None):
                await original((args.channel,'off',args.case), dest, sdk)
            summary = dest/'summary.json'
            data = json.loads(summary.read_text())
            data['arm'] = args.arm
            data['route_version'] = 'structured-v1' if args.structured else 'overnight-route-v1'
            data['structured_fraud'] = args.structured
            decisions_file = dest/'route-decisions.jsonl'
            rows = [json.loads(line) for line in decisions_file.read_text().splitlines()] if decisions_file.exists() else []
            stops = [row for row in rows if row.get('action') == 'CLOSE_STOP']
            data['paid_stop_evidence'] = []
            if stops:
                direct = dest/'direct-trace.json'
                if direct.exists():
                    traces = json.loads(direct.read_text())
                else:
                    traces = {}
                    for path in (dest/'traces').glob('*.json'):
                        item = json.loads(path.read_text())
                        if item.get('workflow_id'):
                            traces[item['workflow_id']] = item
                for row in stops:
                    binding = row['settlement']
                    trace = traces.get(binding['workflow_id'], {})
                    steps = trace.get('steps', [])
                    notified = notification_evidence(steps, binding)
                    completed = any(s.get('kind')=='tool' and s.get('agent')=='orchestrator_agent'
                                    and s.get('name')=='complete_task' and not s.get('error')
                                    and (s.get('output') or {}).get('task_status')=='success' for s in steps
                                    if isinstance(s.get('output'), dict))
                    transactions = data.get('transactions', [])
                    unchanged = (len(transactions) == 1 and transactions[0].get('transfer_id') == binding['transfer_id']
                                 and transactions[0].get('invoice_id') == binding['invoice_id']
                                 and transactions[0].get('amount') == binding['amount']
                                 and transactions[0].get('status') == 'completed')
                    data['paid_stop_evidence'].append({'notification_observed':notified,
                        'orchestrator_completed':completed,'prior_payment_unchanged':unchanged,
                        'trace_checks_passed':bool(notified and completed and unchanged)})
            summary.write_text(json.dumps(data, indent=2)+'\n')
        finally:
            verifier.setup_guard = original_setup
    study_live.execute = execute
    try:
        await run(case_id, legacy, (args.channel,'off',args.case))
    finally:
        study_live.execute = original


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--channel', choices=('direct','portal','chat','onboarding'), required=True)
    parser.add_argument('--arm', choices=ARMS, required=True)
    parser.add_argument('--case', required=True)
    parser.add_argument('--fixtures', required=True)
    parser.add_argument('--structured', action='store_true', help='OFF only: separate Fraud-output-format contrast')
    asyncio.run(main(parser.parse_args()))
