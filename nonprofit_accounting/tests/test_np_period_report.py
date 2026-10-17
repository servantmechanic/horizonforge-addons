from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNpPeriodReport(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        acc = {code: ref(f"nonprofit_accounting.np_account_{code}") for code in (
            "1000", "1050", "2100", "3000", "4010", "4020", "4900", "5000", "5300", "6950",
        )}
        cls.checking, cls.petty_cash = acc["1000"], acc["1050"]
        cls.acc = acc
        Move = cls.env["np.move"]

        def journal(date, *lines, post=True):
            move = Move.create({
                "move_type": "journal",
                "date": date,
                "item_line_ids": [
                    Command.create({"account_id": account.id, "debit": debit, "credit": credit})
                    for account, debit, credit in lines
                ],
            })
            if post:
                move.action_post()
            return move

        def simple(move_type, date, bank, account, amount, post=True):
            move = Move.create({
                "move_type": move_type,
                "date": date,
                "bank_account_id": bank.id,
                "item_line_ids": [Command.create({"account_id": account.id, "amount": amount})],
            })
            if post:
                move.action_post()
            return move

        # Opening balances
        journal("2026-08-31", (cls.checking, 5000, 0), (acc["3000"], 0, 5000))
        journal("2026-08-31", (cls.petty_cash, 100, 0), (acc["3000"], 0, 100))
        # September
        simple("deposit", "2026-09-05", cls.checking, acc["4010"], 10000)
        simple("deposit", "2026-09-06", cls.checking, acc["4020"], 4000)
        simple("payment", "2026-09-10", cls.checking, acc["5300"], 800)
        transfer = Move.create({
            "move_type": "transfer",
            "date": "2026-09-12",
            "bank_account_id": cls.checking.id,
            "dest_account_id": cls.petty_cash.id,
            "amount": 200,
        })
        transfer.action_post()
        simple("payment", "2026-09-15", cls.petty_cash, acc["6950"], 50)
        # Payroll: 3000 gross, 400 withheld, 2600 paid from checking
        journal("2026-09-30", (acc["5000"], 3000, 0), (acc["2100"], 0, 400), (cls.checking, 0, 2600))
        # Not cash / not posted / not in the period: all ignored
        journal("2026-09-20", (acc["2100"], 100, 0), (acc["4900"], 0, 100))
        simple("deposit", "2026-09-25", cls.checking, acc["4900"], 999, post=False)
        simple("deposit", "2026-10-01", cls.checking, acc["4900"], 777)

    def _report(self, banks=None):
        wizard = self.env["np.period.report"].create({
            "date_from": "2026-09-01",
            "date_to": "2026-09-30",
            "bank_account_ids": [Command.set(banks.ids)] if banks else [],
        })
        return wizard, wizard._get_report_data()

    def _amounts(self, rows):
        return {row["account"].code: row["amount"] for row in rows}

    def test_all_accounts(self):
        _wizard, data = self._report()
        self.assertEqual(data["beginning"], 5100)
        self.assertEqual(self._amounts(data["income_rows"]), {"4010": 10000, "4020": 4000})
        self.assertEqual(self._amounts(data["expense_rows"]), {"5000": 3000, "5300": 800, "6950": 50})
        self.assertEqual(data["total_income"], 14000)
        self.assertEqual(data["total_expense"], 3850)
        self.assertFalse(data["transfer_rows"], "transfers between selected accounts cancel out")
        self.assertEqual(self._amounts(data["other_rows"]), {"2100": 400})
        self.assertEqual(data["ending"], 15650)
        self.assertTrue(data["balanced"])

    def test_one_account(self):
        _wizard, data = self._report(self.checking)
        self.assertEqual(data["beginning"], 5000)
        self.assertEqual(data["total_income"], 14000)
        self.assertEqual(data["total_expense"], 3800)
        self.assertEqual(self._amounts(data["transfer_rows"]), {"1050": -200})
        self.assertEqual(data["ending"], 15400)
        self.assertTrue(data["balanced"])

    def test_renders(self):
        wizard, _data = self._report()
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            "nonprofit_accounting.report_period", wizard.ids
        )
        html = html.decode()
        self.assertIn("Beginning Balance", html)
        self.assertIn(self.env.company.name, html, "company name comes from the company record")
        self.assertIn("4010 North District Support", html)
        self.assertNotIn("Does not tie out", html)

    def _drill(self, wizard, kind, **kwargs):
        action = wizard.action_drilldown(kind, **kwargs)
        return self.env["np.move.line"].search(action["domain"])

    def test_drilldown(self):
        wizard, data = self._report()
        north = self._drill(wizard, "account", account_id=self.acc["4010"].id)
        self.assertEqual(sum(north.mapped("report_amount")), 10000)
        income = self._drill(wizard, "section", section="income")
        self.assertEqual(sum(income.mapped("report_amount")), data["total_income"])
        expenses = self._drill(wizard, "section", section="expense")
        self.assertEqual(sum(expenses.mapped("report_amount")), data["total_expense"])
        beginning = self._drill(wizard, "beginning")
        self.assertEqual(sum(beginning.mapped("balance")), data["beginning"])
        ending = self._drill(wizard, "ending")
        self.assertEqual(sum(ending.mapped("balance")), data["ending"])
        checking_activity = self._drill(wizard, "bank_period", account_id=self.checking.id)
        row = next(r for r in data["bank_rows"] if r["account"] == self.checking)
        self.assertEqual(sum(checking_activity.mapped("balance")), row["ending"] - row["beginning"])

    def test_drilldown_links_render(self):
        wizard, _data = self._report()
        html = self.env["ir.actions.report"]._render_qweb_html(
            "nonprofit_accounting.report_period", wizard.ids
        )[0].decode()
        self.assertIn(f'data-np-report-id="{wizard.id}"', html)
        self.assertIn(f'data-np-account="{self.acc["4010"].id}"', html)

    def test_open_entry_and_partner_button(self):
        line = self.env["np.move.line"].search([("account_id", "=", self.acc["4010"].id)], limit=1)
        self.assertEqual(line.action_open_move()["res_id"], line.move_id.id)
        partner = self.env["res.partner"].create({"name": "Supply Co"})
        self.env["np.move"].create({"move_type": "payment", "partner_id": partner.id})
        self.assertEqual(partner.np_entry_count, 1)
        self.assertEqual(partner.action_np_open_entries()["domain"], [("partner_id", "=", partner.id)])

    def test_date_order(self):
        with self.assertRaises(ValidationError):
            self.env["np.period.report"].create({"date_from": "2026-09-30", "date_to": "2026-09-01"})
