from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestNpMove(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.checking = ref("nonprofit_accounting.np_account_1000")
        cls.petty_cash = ref("nonprofit_accounting.np_account_1050")
        cls.net_assets = ref("nonprofit_accounting.np_account_3000")
        cls.tuition = ref("nonprofit_accounting.np_account_4010")
        cls.supplies = ref("nonprofit_accounting.np_account_5300")
        cls.bank_fees = ref("nonprofit_accounting.np_account_6900")
        cls.district = cls.env["res.partner"].create({"name": "Example School District"})
        cls.env.company.np_lock_date = False

    def _deposit(self, *items, date="2026-09-15"):
        return self.env["np.move"].create({
            "move_type": "deposit",
            "date": date,
            "bank_account_id": self.checking.id,
            "partner_id": self.district.id,
            "item_line_ids": [
                Command.create({"account_id": account.id, "amount": amount})
                for account, amount in (items or [(self.tuition, 1000.0)])
            ],
        })

    def _line(self, move, account):
        return move.line_ids.filtered(lambda line: line.account_id == account)

    def test_deposit_generates_bank_line(self):
        move = self._deposit()
        bank_line = self._line(move, self.checking)
        income_line = self._line(move, self.tuition)
        self.assertTrue(bank_line.is_generated)
        self.assertEqual((bank_line.debit, bank_line.credit), (1000.0, 0.0))
        self.assertEqual((income_line.debit, income_line.credit), (0.0, 1000.0))
        self.assertEqual(income_line.partner_id, self.district)
        self.assertEqual(move.amount_total, 1000.0)

        move.action_post()
        self.assertEqual(move.state, "posted")
        self.assertTrue(move.name.startswith("DEP/2026/"))

    def test_deposit_with_fee_deducted(self):
        move = self._deposit((self.tuition, 1000.0), (self.bank_fees, -25.0))
        self.assertEqual(self._line(move, self.checking).debit, 975.0)
        self.assertEqual(self._line(move, self.bank_fees).debit, 25.0)
        move.action_post()

    def _bill(self, amount=80.0):
        return self.env["np.move"].create({
            "move_type": "payment",
            "bill_date": "2026-09-10",
            "partner_id": self.district.id,
            "ref": "INV-778",
            "item_line_ids": [Command.create({"account_id": self.supplies.id, "amount": amount})],
        })

    def _pay(self, bill, **vals):
        action = bill.action_open_pay_wizard()
        wizard = self.env["np.move.pay"].with_context(action["context"]).create(vals)
        wizard.action_pay()
        return wizard

    def test_bill_then_pay(self):
        bill = self._bill()
        self.assertEqual(bill.payment_state, "unpaid")
        self.assertEqual(bill.state, "draft")

        wizard = self._pay(bill, bank_account_id=self.checking.id, check_number="1042")
        self.assertEqual(str(wizard.paid_date), "2026-09-10", "paid date defaults to the bill date")
        self.assertEqual(bill.payment_state, "paid")
        self.assertEqual(str(bill.date), "2026-09-10")
        self.assertEqual(bill.check_number, "1042")
        self.assertTrue(bill.name.startswith("PAY/2026/"))
        self.assertEqual(self._line(bill, self.supplies).debit, 80.0)
        self.assertEqual(self._line(bill, self.checking).credit, 80.0)

    def test_pay_on_a_later_date(self):
        bill = self._bill()
        self._pay(bill, paid_date="2026-09-25", bank_account_id=self.checking.id)
        self.assertEqual(str(bill.date), "2026-09-25")
        self.assertEqual(str(bill.bill_date), "2026-09-10")

    def test_pay_into_locked_period(self):
        self.env.company.np_lock_date = "2026-09-15"
        bill = self._bill()
        with self.assertRaises(UserError):
            self._pay(bill, bank_account_id=self.checking.id)
        self._pay(bill, paid_date="2026-09-16", bank_account_id=self.checking.id)
        self.assertEqual(bill.payment_state, "paid")

    def test_pay_from_defaults(self):
        self.env.company.np_default_payment_account_id = self.checking
        first = self._bill()
        self.assertEqual(first.action_open_pay_wizard()["context"]["default_bank_account_id"],
                         self.checking.id, "falls back to the company default")
        self._pay(first, bank_account_id=self.petty_cash.id)

        second = self._bill()
        self.assertEqual(second.action_open_pay_wizard()["context"]["default_bank_account_id"],
                         self.petty_cash.id, "uses the account this vendor was last paid from")

    def test_mark_unpaid(self):
        bill = self._bill()
        self._pay(bill, bank_account_id=self.checking.id, check_number="1042")
        bill.button_draft()
        self.assertEqual(bill.payment_state, "unpaid")

    def test_editing_draft_updates_bank_line(self):
        move = self._deposit()
        move.item_line_ids.amount = 1200.0
        self.assertEqual(self._line(move, self.checking).debit, 1200.0)

    def test_transfer(self):
        move = self.env["np.move"].create({
            "move_type": "transfer",
            "date": "2026-09-01",
            "bank_account_id": self.checking.id,
            "dest_account_id": self.petty_cash.id,
            "amount": 100.0,
        })
        self.assertEqual(self._line(move, self.petty_cash).debit, 100.0)
        self.assertEqual(self._line(move, self.checking).credit, 100.0)
        move.action_post()

        same = move.copy({"dest_account_id": self.checking.id})
        with self.assertRaises(ValidationError):
            same.action_post()

    def test_journal_entry_must_balance(self):
        move = self.env["np.move"].create({
            "move_type": "journal",
            "date": "2026-07-01",
            "item_line_ids": [
                Command.create({"account_id": self.checking.id, "debit": 5000.0}),
                Command.create({"account_id": self.net_assets.id, "credit": 4000.0}),
            ],
        })
        with self.assertRaises(ValidationError):
            move.action_post()

        move.item_line_ids.filtered("credit").credit = 5000.0
        move.action_post()
        self.assertTrue(move.name.startswith("JE/2026/"))

    def test_posted_entry_is_read_only(self):
        move = self._deposit()
        move.action_post()
        with self.assertRaises(UserError):
            move.memo = "changed"
        with self.assertRaises(UserError):
            move.item_line_ids.amount = 1.0
        with self.assertRaises(UserError):
            move.unlink()

    def test_reset_to_draft_keeps_number(self):
        move = self._deposit()
        move.action_post()
        number = move.name
        move.button_draft()
        self.assertEqual(move.state, "draft")
        move.memo = "corrected"
        move.action_post()
        self.assertEqual(move.name, number)

    def test_lock_date(self):
        move = self._deposit(date="2026-08-15")
        move.action_post()
        self.env.company.np_lock_date = "2026-08-31"
        with self.assertRaises(UserError):
            move.button_draft()

        late = self._deposit(date="2026-08-20")
        with self.assertRaises(UserError):
            late.action_post()
        late.date = "2026-09-01"
        late.action_post()

    def test_delete(self):
        self._deposit().unlink()

        move = self._deposit()
        move.action_post()
        move.button_draft()
        with self.assertRaises(UserError):
            move.unlink()

    def test_viewer_is_read_only(self):
        viewer = new_test_user(
            self.env,
            login="np_viewer",
            groups="base.group_user,nonprofit_accounting.group_np_viewer",
        )
        move = self._deposit()
        move.action_post()
        self.assertEqual(move.with_user(viewer).amount_total, 1000.0)
        with self.assertRaises(AccessError):
            move.with_user(viewer).button_draft()
        with self.assertRaises(AccessError):
            self.env["np.move"].with_user(viewer).create({"move_type": "journal"})


@tagged("post_install", "-at_install")
class TestNpDashboard(TestNpMove):

    def test_balance_and_drafts(self):
        self._deposit().action_post()
        self._deposit()
        self.assertEqual(self.checking.balance, 1000.0, "only posted entries count")
        self.assertEqual(self.checking.draft_count, 1)

    def test_unpaid_bills_summary(self):
        self.env.company.np_default_payment_account_id = self.checking
        self._bill(80.0)
        self._bill(20.0)
        self.assertTrue(self.checking.show_unpaid_bills)
        self.assertFalse(self.petty_cash.show_unpaid_bills)
        self.assertEqual(self.checking.unpaid_bill_count, 2)
        self.assertEqual(self.checking.unpaid_bill_total, 100.0)

    def test_quick_actions(self):
        action = self.checking.action_new_bill()
        self.assertEqual(action["context"]["default_move_type"], "payment")
        self.assertEqual(action["context"]["default_bank_account_id"], self.checking.id)
        self.assertEqual(self.checking.action_open_entries()["domain"],
                         [("account_id", "=", self.checking.id)])
