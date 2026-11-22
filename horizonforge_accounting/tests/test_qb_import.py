from base64 import b64encode
from datetime import date
from pathlib import Path

from odoo.exceptions import UserError
from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.horizonforge_accounting.wizard import qb_parse

FIXTURES = Path(__file__).parent / "fixtures" / "qbo"


def _file(name):
    return b64encode((FIXTURES / name).read_bytes())


@tagged("post_install", "-at_install")
class TestQbImport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]

    def _wizard(self, history=False):
        vals = {
            "company_id": self.company.id,
            "cutover_date": "2025-12-31",
            "account_list_file": _file("account_list.csv"),
            "account_list_filename": "account_list.csv",
            "trial_balance_file": _file("trial_balance.csv"),
            "trial_balance_filename": "trial_balance.csv",
            "ar_aging_file": _file("ar_aging.csv"),
            "ar_aging_filename": "ar_aging.csv",
            "ap_aging_file": _file("ap_aging.csv"),
            "ap_aging_filename": "ap_aging.csv",
            "customers_file": _file("customers.csv"),
            "customers_filename": "customers.csv",
        }
        if history:
            vals.update(pl_history_file=_file("pl_by_month.csv"), pl_history_filename="pl_by_month.csv")
        wizard = self.env["hf.qb.import"].create(vals)
        wizard.action_analyze()
        return wizard

    def _line(self, wizard, name):
        return wizard.line_ids.filtered(lambda l: l.qb_name == name)

    def _balance(self, account, date_to="2025-12-31", date_from=None):
        domain = [("account_id", "=", account.id), ("parent_state", "=", "posted"), ("date", "<=", date_to)]
        if date_from:
            domain.append(("date", ">=", date_from))
        return round(sum(self.env["account.move.line"].search(domain).mapped("balance")), 2)

    def test_parsers(self):
        rows = qb_parse.read_rows((FIXTURES / "trial_balance.csv").read_bytes(), "tb.csv")
        lines = qb_parse.parse_trial_balance(rows)
        self.assertEqual(len(lines), 12)
        self.assertEqual(sum(line["balance"] for line in lines), 0.0)
        rows = qb_parse.read_rows((FIXTURES / "ar_aging.csv").read_bytes(), "ar.csv")
        aging = qb_parse.parse_aging(rows, ["customer"])
        self.assertEqual([e["open_balance"] for e in aging], [2000.0, 1500.0, -500.0])
        self.assertEqual(aging[0]["due_date"], date(2026, 1, 14))
        self.assertEqual(qb_parse.parse_amount("(1,234.50)"), -1234.5)
        self.assertEqual(qb_parse.parse_amount("$77,000.00"), 77000.0)

    def test_mapping_proposal(self):
        wizard = self._wizard()
        self.assertEqual(wizard.state, "map")
        receivable = self._line(wizard, "Accounts Receivable (A/R)")
        self.assertEqual((receivable.role, receivable.action), ("receivable", "map"))
        self.assertEqual(receivable.account_id.account_type, "asset_receivable")
        self.assertEqual(self._line(wizard, "Retained Earnings").account_id,
                         self.company.get_unaffected_earnings_account())
        # Matched by name to the starter account.
        self.assertEqual(self._line(wizard, "Job Materials").account_id,
                         self.env.ref(self.company._hf_xmlid("job_materials")))
        gas = self._line(wizard, "Utilities:Gas and Electric")
        self.assertEqual((gas.action, gas.new_name, gas.new_account_type), ("create", "Gas and Electric", "expense"))
        self.assertEqual(self._line(wizard, "Visa").new_account_type, "liability_credit_card")
        self.assertEqual(self._line(wizard, "Truck").balance, 30000.0)
        codes = wizard.line_ids.filtered(lambda l: l.action == "create").mapped("new_code")
        self.assertEqual(len(codes), len(set(codes)))
        self.assertNotIn("differs", wizard.summary)

    def test_import_ties_out(self):
        wizard = self._wizard()
        wizard.action_import()
        self.assertEqual(wizard.state, "done")
        self.assertIn("ties out", wizard.result)
        clearing = self.env.ref(wizard._xmlid("qb_clearing"))
        self.assertEqual(self._balance(clearing), 0.0)
        expected = {
            "Checking": 12500.0,
            "Accounts Receivable (A/R)": 3000.0,
            "Truck": 30000.0,
            "Accounts Payable (A/P)": -1200.0,
            "Visa": -800.0,
            "Truck Loan": -20000.0,
            "Owner's Investment": -10000.0,
            "Retained Earnings": -5000.0,
            "Sales": -40000.0,
            "Utilities:Gas and Electric": 1500.0,
            "Depreciation": 15000.0,
        }
        for name, amount in expected.items():
            self.assertEqual(self._balance(self._line(wizard, name).account_id), amount, name)
        self.assertEqual(self._line(wizard, "Depreciation").account_id.account_type, "expense_depreciation")

    def test_open_items(self):
        wizard = self._wizard()
        wizard.action_import()
        invoices = wizard.move_ids.filtered(lambda m: m.move_type in ("out_invoice", "out_refund"))
        self.assertEqual(sorted(invoices.mapped("amount_total_signed")), [-500.0, 1500.0, 2000.0])
        smith = invoices.filtered(lambda m: m.ref == "1001")
        self.assertEqual(smith.partner_id.email, "office@smith.example")
        self.assertEqual((smith.invoice_date, smith.date, smith.invoice_date_due),
                         (date(2025, 12, 15), date(2025, 12, 31), date(2026, 1, 14)))
        self.assertEqual(smith.payment_state, "not_paid")
        bill = wizard.move_ids.filtered(lambda m: m.move_type == "in_invoice")
        self.assertEqual((bill.partner_id.name, bill.ref, bill.amount_total), ("Lumber Yard", "INV-55", 1200.0))
        self.assertTrue(bill.partner_id.supplier_rank)

    def test_bank_journals(self):
        wizard = self._wizard()
        wizard.action_import()
        for name in ("Checking", "Visa"):
            account = self._line(wizard, name).account_id
            journal = self.env["account.journal"].search([("default_account_id", "=", account.id)])
            self.assertEqual(journal.type, "bank", name)

    def test_history(self):
        wizard = self._wizard(history=True)
        wizard.action_import()
        self.assertIn("ties out", wizard.result)
        sales = self._line(wizard, "Sales").account_id
        self.assertEqual(self._balance(sales, "2025-01-31", "2025-01-01"), -20000.0)
        self.assertEqual(self._balance(sales), -40000.0)
        gas = self._line(wizard, "Utilities:Gas and Electric").account_id
        self.assertEqual(self._balance(gas, "2025-01-31"), 750.0)
        retained = self.company.get_unaffected_earnings_account()
        self.assertEqual(self._balance(retained), -5000.0)
        self.assertEqual(self._balance(self._line(wizard, "Checking").account_id), 12500.0)

    def test_aging_mismatch_left_in_clearing(self):
        wizard = self._wizard()
        wizard.ap_aging_file = False
        wizard.action_analyze()
        self.assertIn("differs", wizard.summary)
        wizard.action_import()
        self.assertIn("not zero", wizard.result)
        clearing = self.env.ref(wizard._xmlid("qb_clearing"))
        self.assertEqual(self._balance(clearing), -1200.0)

    def test_import_once(self):
        self._wizard().action_import()
        with self.assertRaisesRegex(UserError, "already imported"):
            self._wizard().action_import()

    def test_missing_mapping(self):
        wizard = self._wizard()
        line = self._line(wizard, "Truck")
        line.write({"action": "map", "account_id": False})
        with self.assertRaisesRegex(UserError, "Choose an account for Truck"):
            wizard.action_import()
