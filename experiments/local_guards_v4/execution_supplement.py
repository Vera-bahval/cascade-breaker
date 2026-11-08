"""One additional post-freeze native scenario: reconciled failed workflow retry.

Uses the existing scripted fixture, native chat/background runner and store.
Reconciliation is an explicit trusted test action after inspecting native DB;
there is no new user API and no claim that the runtime infers a safe retry.
"""
import argparse
import json
from pathlib import Path
import unittest
from .tests.test_runtime import NativeRuntimeTests, tool, done, Runtime, CoPilotAssistant
from finbot.core.data.database import db_session
from finbot.core.data.models import Invoice
from finbot.mcp.servers.finstripe.models import PaymentTransaction
from starlette.background import BackgroundTasks


class ReconciledRetry(NativeRuntimeTests):
    async def test_known_no_effect_failure_can_be_reconciled_then_retried(self):
        scripts = {'orchestrator_agent': [[tool('complete_task', task_status='failed',
                                               task_summary='Scripted failure before any effect')]]}
        self.script(scripts)
        first = BackgroundTasks()
        chat = CoPilotAssistant(self.session, first)
        with self.runtime.agent_scope(chat, {'vendor_id': 2}):
            await chat._execute_tool('start_workflow', {'description': 'scripted',
                                                     'vendor_id': 2, 'invoice_id': 3})
            child = first.tasks[0].args[0]
        await first()
        self.assertEqual(child.store.claim(child.owner)['state'], 'uncertain')
        with db_session() as db:
            self.assertEqual(db.query(PaymentTransaction).count(), 0)
            self.assertEqual(db.get(Invoice, 3).status, 'submitted')
        # A trusted reconciler has now confirmed the failed run had no effect.
        child.store.release_claim(child.owner, known_outcome=True)
        scripts['orchestrator_agent'].append([done()])
        retry = Runtime(self.path, 'B', fixture_contract=self.runtime.fixture)
        second = BackgroundTasks()
        second_chat = CoPilotAssistant(self.session, second)
        with retry.agent_scope(second_chat, {'vendor_id': 2}):
            await second_chat._execute_tool('start_workflow', {'description': 'scripted retry',
                                                            'vendor_id': 2, 'invoice_id': 3})
            next_child = second.tasks[0].args[0]
        self.assertNotEqual(child.owner, next_child.owner)
        await second()
        self.assertEqual(next_child.store.claim(next_child.owner)['state'], 'released')
        self.assertEqual(self.calls, ['orchestrator_agent', 'orchestrator_agent'])


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    if args.output.exists():
        raise ValueError('refusing overwrite')
    # An explicit one-test suite avoids rerunning inherited existing tests.
    suite = unittest.TestSuite([ReconciledRetry('test_known_no_effect_failure_can_be_reconciled_then_retried')])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    record = {'phase': 'post_freeze_additional_native_execution', 'tests': result.testsRun,
              'successful': result.wasSuccessful(), 'new_inference_api_calls': 0,
              'reconciliation': 'explicit trusted store release after native DB confirmed no effect',
              'limitation': 'No automatic semantic failure classification or public retry API added.'}
    args.output.write_text(json.dumps(record, indent=2) + '\n')
    return int(not result.wasSuccessful())


if __name__ == '__main__':
    raise SystemExit(main())
