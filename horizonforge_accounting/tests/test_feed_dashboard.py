import json
from datetime import date, datetime
from unittest.mock import patch

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

PLAID_RETRIEVE = (
    "odoo.addons.account_statement_import_online_plaid.models."
    "online_bank_statement_provider_plaid.OnlineBankStatementProvider._plaid_retrieve_data"
)


@tagged("post_install", "-at_install")
class TestFeedDashboard(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.journal = cls.company_data["default_journal_bank"]
        cls.journal.write({
            "bank_statements_source": "online",
            "online_bank_statement_provider": "plaid",
        })
        cls.provider = cls.journal.online_bank_statement_provider_id
        cls.provider.write({"plaid_account_id": "checking", "tz": "UTC"})

    def _feed(self, journal=None):
        journal = journal or self.journal
        journal.invalidate_recordset(["kanban_dashboard"])
        return json.loads(journal.kanban_dashboard).get("hf_feed")

    def _line(self, day, amount, ref):
        return {
            "date": datetime(2026, 10, day),
            "payment_ref": ref,
            "amount": amount,
            "unique_import_id": ref,
        }

    def test_status_not_synced(self):
        self.assertEqual(self._feed(), {"last_sync": False, "error": False})
        other = self.company_data["default_journal_cash"]
        self.assertIsNone(self._feed(other))

    def test_sync_now(self):
        self.provider.last_successful_run = datetime(2026, 10, 1)
        self.provider.hf_last_error = "old error"
        with patch(PLAID_RETRIEVE, return_value=[self._line(2, -45.0, "fuel")]):
            self.journal.action_hf_sync_feed()
        lines = self.env["account.bank.statement.line"].search([("journal_id", "=", self.journal.id)])
        self.assertEqual((lines.date, lines.amount), (date(2026, 10, 2), -45.0))
        self.assertGreater(self.provider.last_successful_run, datetime(2026, 10, 1))
        feed = self._feed()
        self.assertFalse(feed["error"])
        self.assertTrue(feed["last_sync"])

    def test_scheduled_failure_and_recovery(self):
        self.provider.last_successful_run = datetime(2026, 10, 1)
        scheduled = self.provider.with_context(scheduled=True)
        with patch(PLAID_RETRIEVE, side_effect=ValueError("bank is down")):
            scheduled._pull(datetime(2026, 10, 1), datetime(2026, 10, 2))
        self.assertEqual(self._feed()["error"], "bank is down")
        with patch(PLAID_RETRIEVE, return_value=[]):
            scheduled._pull(datetime(2026, 10, 1), datetime(2026, 10, 2))
        self.assertFalse(self._feed()["error"])
