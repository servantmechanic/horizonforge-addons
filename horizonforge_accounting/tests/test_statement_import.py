from base64 import b64encode
from datetime import date
from pathlib import Path

from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon

FIXTURES = Path(__file__).parent / "fixtures"


@tagged("post_install", "-at_install")
class TestStatementImport(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.card = cls.env["account.journal"].search([
            ("company_id", "=", cls.company.id),
            ("code", "=", "CARD"),
        ])

    def _import(self, map_xmlid, filename, journal=None):
        journal = journal or self.card
        wizard = self.env["account.statement.import"].with_context(journal_id=journal.id).create({
            "statement_filename": filename,
            "statement_file": b64encode((FIXTURES / filename).read_bytes()),
            "sheet_mapping_id": self.env.ref(f"horizonforge_accounting.{map_xmlid}").id,
        })
        wizard.import_file_button()
        return self.env["account.bank.statement.line"].search([("journal_id", "=", journal.id)], order="date, id")

    def _assert_lines(self, lines, expected):
        self.assertEqual(
            [(line.date, line.payment_ref, line.amount) for line in lines],
            expected,
        )

    def test_card_maps(self):
        # On a card journal purchases are money out (negative) and payments
        # money in (positive), whatever sign the issuer's file uses.
        cases = [
            ("map_chase_card", "chase_card.csv", "HOME DEPOT #123", 245.17, "Payment Thank You-Mobile", 500.0),
            ("map_amex", "amex.csv", "LOWES #0456", 312.40, "AUTOPAY PAYMENT - THANK YOU", 312.40),
            ("map_discover", "discover.csv", "SHELL OIL 5741", 58.20, "INTERNET PAYMENT - THANK YOU", 58.20),
            ("map_capital_one", "capital_one.csv", "MENARDS", 1075.0, "CAPITAL ONE ONLINE PYMT", 1075.0),
            ("map_citi", "citi.csv", "FASTENAL CO", 89.99, "PAYMENT THANK YOU", 89.99),
        ]
        for map_xmlid, filename, purchase, purchase_amount, payment, payment_amount in cases:
            with self.subTest(map=map_xmlid):
                lines = self._import(map_xmlid, filename)
                self._assert_lines(lines, [
                    (date(2026, 10, 2), purchase, -purchase_amount),
                    (lines[1].date, payment, payment_amount),
                ])
                lines.statement_id.unlink()
                lines.unlink()

    def test_bank_maps(self):
        checking = self.company_data["default_journal_bank"]
        lines = self._import("map_chase_checking", "chase_checking.csv", checking)
        self._assert_lines(lines, [
            (date(2026, 10, 2), "CHECK 1042", -1200.0),
            (date(2026, 10, 5), "DEPOSIT", 3450.0),
        ])
        self.assertEqual(lines[0].ref, "1042")
        lines.statement_id.unlink()
        lines.unlink()
        lines = self._import("map_wells_fargo", "wells_fargo.csv", checking)
        self._assert_lines(lines, [
            (date(2026, 10, 2), "VERIZON WIRELESS", -64.10),
            (date(2026, 10, 5), "MOBILE DEPOSIT", 2500.0),
        ])

    def test_owner_reconcile_models(self):
        for key, account_key in [("reco_owner_draw", "owner_draws"), ("reco_owner_contribution", "owner_contributions")]:
            model = self.env.ref(self.company._hf_xmlid(key))
            self.assertEqual(model.company_id, self.company)
            self.assertEqual(model.line_ids.account_id, self.env.ref(self.company._hf_xmlid(account_key)))
