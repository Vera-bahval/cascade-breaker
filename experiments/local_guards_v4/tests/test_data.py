import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prepare_data import bookkeeping_receipt, lineage, pair_transfers, session_at_cut


class CustodianTests(unittest.TestCase):
    def test_session_lower_bound_uses_only_current_cut(self):
        start = "2026-10-01T10:00:00Z"
        self.assertIs(session_at_cut(start, "2026-10-01T11:59:59Z"), True)
        self.assertIsNone(session_at_cut(start, "2026-10-01T12:00:00Z"))
        self.assertIsNone(session_at_cut(start, "2026-10-01T09:59:59Z"))
        self.assertIsNone(session_at_cut(None, "2026-10-01T10:00:01Z"))

    def test_completion_requires_exact_pending_call_and_lineage(self):
        before = {"hook_kind": "before_tool", "tool_name": "finstripe__create_transfer", "session_id": "s", "workflow_id": "w", "tool_arguments": {"amount": 10}}
        after = dict(before, hook_kind="after_tool", tool_result={"status": "completed"})
        self.assertEqual(pair_transfers([before, after]), (True, [6]))
        self.assertFalse(pair_transfers([before, dict(after, workflow_id="other")])[0])
        self.assertFalse(pair_transfers([before, dict(after, tool_arguments={"amount": 100})])[0])
        self.assertFalse(pair_transfers([after])[0])
        self.assertFalse(pair_transfers([before])[0])

    def test_bookkeeping_receipt_is_pre_cut_scoped_and_reference_matching(self):
        before = {"hook_kind": "before_tool", "tool_name": "finstripe__create_transfer", "session_id": "s", "workflow_id": "w", "tool_arguments": {"amount": 10, "invoice_id": 7, "vendor_id": 3}}
        after = dict(before, hook_kind="after_tool", tool_result={"status": "completed", "transfer_id": "t", "amount": 10, "currency": "usd"})
        proposal = {"event_seq": 2, "checkpoint": "P4", "facts": {"recipient_matches_authorized": True}}
        current = {"facts": {"prior_completed_transfers": 1, "invoice_amount": "10", "invoice_currency": "USD"}}
        args = {"invoice_id": 7, "payment_reference": "t"}
        scope = {"namespace": "n", "session_id": "s", "workflow_id": "w", "invoice_id": 7, "vendor_id": 3}
        self.assertIs(bookkeeping_receipt([before, after], 6, args, [proposal], current, scope), True)
        self.assertIsNone(bookkeeping_receipt([before, after], 4, args, [proposal], current, scope))
        self.assertIs(bookkeeping_receipt([before, after], 6, dict(args, payment_reference="forged"), [proposal], current, scope), False)
        self.assertIsNone(bookkeeping_receipt([before, dict(after, workflow_id="other")], 6, args, [proposal], current, scope))
        self.assertIsNone(bookkeeping_receipt([before, after], 6, args, [proposal], current, dict(scope, vendor_id=8)))
        self.assertIsNone(bookkeeping_receipt([before, after], 6, args, [proposal], current, dict(scope, workflow_id="other")))
        self.assertIsNone(bookkeeping_receipt([before, after], 6, args, [proposal], current))

    def test_actor_lineage_does_not_recover_after_mismatched_return(self):
        before = {"hook_kind": "before_tool", "tool_name": "delegate_to_invoice", "session_id": "s", "workflow_id": "w", "tool_arguments": {"invoice_id": 1}}
        bad = dict(before, hook_kind="after_tool", tool_name="delegate_to_fraud")
        later = dict(before, tool_name="get_invoice_details")
        actors = lineage([before, bad, later])
        self.assertIsNone(actors[6])


if __name__ == "__main__":
    unittest.main()
