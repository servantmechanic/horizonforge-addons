from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestNpReconciliation(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.checking = ref("nonprofit_accounting.np_account_1000")
        cls.petty_cash = ref("nonprofit_accounting.np_account_1050")
        cls.net_assets = ref("nonprofit_accounting.np_account_3000")
        cls.north = ref("nonprofit_accounting.np_account_4010")
        cls.supplies = ref("nonprofit_accounting.np_account_5300")
        cls.env.company.np_lock_date = False

        cls.opening = cls._post(cls.env["np.move"].create({
            "move_type": "journal",
            "date": "2026-08-31",
            "item_line_ids": [
                Command.create({"account_id": cls.checking.id, "debit": 5000}),
                Command.create({"account_id": cls.net_assets.id, "credit": 5000}),
            ],
        }))
        cls.deposit = cls._post(cls._simple("deposit", "2026-09-05", cls.north, 10000))
        cls.check_1001 = cls._post(cls._simple("payment", "2026-09-10", cls.supplies, 800))
        cls.check_1002 = cls._post(cls._simple("payment", "2026-09-28", cls.supplies, 300))
        cls.october = cls._post(cls._simple("deposit", "2026-10-02", cls.north, 2000))
        cls.draft = cls._simple("deposit", "2026-09-20", cls.north, 999)

    @classmethod
    def _simple(cls, move_type, date, account, amount):
        return cls.env["np.move"].create({
            "move_type": move_type,
            "date": date,
            "bank_account_id": cls.checking.id,
            "item_line_ids": [Command.create({"account_id": account.id, "amount": amount})],
        })

    @classmethod
    def _post(cls, move):
        move.action_post()
        return move

    def _bank_line(self, move):
        return move.line_ids.filtered(lambda line: line.account_id == self.checking)

    def _reconcile(self, date="2026-09-30", balance=14200.0):
        return self.env["np.reconciliation"].create({
            "bank_account_id": self.checking.id,
            "statement_date": date,
            "statement_balance": balance,
        })

    def test_loads_uncleared_posted_lines(self):
        rec = self._reconcile()
        self.assertEqual(rec.line_ids.move_id, self.opening | self.deposit | self.check_1001 | self.check_1002)
        self.assertEqual(rec.beginning_balance, 0.0)

    def test_finish_and_carry_forward(self):
        rec = self._reconcile()
        with self.assertRaises(UserError):
            rec.action_finish()

        # Check 1002 hasn't cleared the bank yet.
        (rec.line_ids - self._bank_line(self.check_1002)).write({"rec_cleared": True})
        self.assertEqual(rec.cleared_deposits, 15000.0)
        self.assertEqual(rec.cleared_payments, 800.0)
        self.assertEqual(rec.difference, 0.0)
        rec.action_finish()
        self.assertEqual(rec.state, "done")
        self.assertFalse(self._bank_line(self.check_1002).reconciliation_id, "carried forward")
        self.assertTrue(self._bank_line(self.check_1001).reconciled)
        self.assertEqual(self.checking.last_reconciled_date.isoformat(), "2026-09-30")

        october = self._reconcile(date="2026-10-31", balance=15900.0)
        self.assertEqual(october.beginning_balance, 14200.0)
        self.assertEqual(october.line_ids.move_id, self.check_1002 | self.october)
        october.action_clear_all()
        self.assertEqual(october.difference, 0.0)
        october.action_finish()

    def test_reconciled_entries_are_locked(self):
        rec = self._reconcile()
        rec.action_clear_all()
        rec.statement_balance = 13900.0
        rec.action_finish()
        with self.assertRaises(UserError):
            self.check_1001.button_draft()
        with self.assertRaises(UserError):
            self._bank_line(self.check_1001).rec_cleared = False

        rec.action_reopen()
        self.check_1001.button_draft()
        self.assertFalse(self._bank_line(self.check_1001).reconciliation_id)

    def test_only_latest_can_be_reopened(self):
        september = self._reconcile()
        september.action_clear_all()
        september.statement_balance = 13900.0
        september.action_finish()
        october = self._reconcile(date="2026-10-31", balance=15900.0)
        october.action_clear_all()
        october.action_finish()
        with self.assertRaises(UserError):
            september.action_reopen()
        october.action_reopen()

    def test_refresh_picks_up_new_entries(self):
        rec = self._reconcile()
        self.draft.action_post()
        self.assertNotIn(self.draft, rec.line_ids.move_id)
        rec.action_refresh()
        self.assertIn(self.draft, rec.line_ids.move_id)

    def test_resetting_entry_drops_it_from_reconciliation_in_progress(self):
        rec = self._reconcile()
        self.deposit.button_draft()
        self.assertNotIn(self.deposit, rec.line_ids.move_id)

    def test_one_in_progress_and_date_order(self):
        rec = self._reconcile()
        with self.assertRaises(ValidationError):
            self._reconcile(date="2026-10-31")
        rec.action_clear_all()
        rec.statement_balance = 13900.0
        rec.action_finish()
        with self.assertRaises(ValidationError):
            self._reconcile(date="2026-09-15")

    def test_delete_in_progress_releases_lines(self):
        rec = self._reconcile()
        rec.action_clear_all()
        lines = rec.line_ids
        rec.unlink()
        self.assertFalse(any(lines.mapped("rec_cleared")))
        self.assertFalse(lines.reconciliation_id)
