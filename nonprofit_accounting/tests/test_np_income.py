from odoo import Command
from odoo.tests import Form, TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNpIncome(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.checking = ref("nonprofit_accounting.np_account_1000")
        cls.north_income = ref("nonprofit_accounting.np_account_4010")
        cls.utilities = ref("nonprofit_accounting.np_account_5600")
        cls.north = ref("nonprofit_accounting.np_partner_north")
        cls.south = ref("nonprofit_accounting.np_partner_south")

    def test_starter_districts(self):
        self.assertEqual(self.north.np_income_account_id, self.north_income)
        self.assertEqual(self.south.np_income_account_id.code, "4020")

    def test_district_prefills_deposit_line(self):
        form = Form(self.env["np.move"].with_context(default_move_type="deposit"))
        form.bank_account_id = self.checking
        form.partner_id = self.north
        with form.item_line_ids.new() as line:
            self.assertEqual(line.account_id, self.north_income)
            line.amount = 5000.0
        move = form.save()
        self.assertEqual(move.item_line_ids.account_id, self.north_income)

    def test_vendor_prefills_bill_line(self):
        vendor = self.env["res.partner"].create({
            "name": "Electric Co-op",
            "np_expense_account_id": self.utilities.id,
        })
        form = Form(self.env["np.move"].with_context(default_move_type="payment"))
        form.partner_id = vendor
        with form.item_line_ids.new() as line:
            self.assertEqual(line.account_id, self.utilities)
            line.amount = 210.0
        form.save()

    def test_report_amount_is_positive(self):
        deposit = self.env["np.move"].create({
            "move_type": "deposit",
            "bank_account_id": self.checking.id,
            "partner_id": self.north.id,
            "item_line_ids": [Command.create({"account_id": self.north_income.id, "amount": 5000.0})],
        })
        deposit.action_post()
        income_line = deposit.line_ids.filtered(lambda line: line.account_type == "income")
        bank_line = deposit.line_ids.filtered(lambda line: line.account_type == "bank")
        self.assertEqual(income_line.report_amount, 5000.0)
        self.assertEqual(bank_line.report_amount, 5000.0)
        self.assertEqual(income_line.partner_id, self.north, "income is tracked by source")
