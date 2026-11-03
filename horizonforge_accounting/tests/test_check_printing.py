import json

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import Form, tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.account_check_printing.models.account_payment import INV_LINES_PER_STUB
from odoo.addons.horizonforge_accounting.models.res_company import QB_VOUCHER_LAYOUT


@tagged("post_install", "-at_install")
class TestCheckPrinting(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        cls.bank = cls.company_data["default_journal_bank"]
        cls.check_method = cls.bank.outbound_payment_method_line_ids.filtered(
            lambda line: line.code == "check_printing"
        )
        cls.check_method.payment_account_id = cls.inbound_payment_method_line.payment_account_id
        cls.partner_a.write({"street": "12 Mill Rd", "city": "Springfield", "zip": "65801"})

    def _pay_by_check(self, count=1, amount=250.0):
        bills = self.env["account.move"].create([{
            "move_type": "in_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-10-01",
            "ref": f"B-{n}",
            "invoice_line_ids": [Command.create({
                "product_id": self.product_a.id,
                "price_unit": amount,
                "tax_ids": [],
            })],
        } for n in range(count)])
        bills.action_post()
        return self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=bills.ids,
        ).create({
            "group_payment": True,
            "payment_method_line_id": self.check_method.id,
        })._create_payments()

    def _html(self, payment):
        return self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_accounting.print_check_qb_voucher", payment.ids,
        )[0].decode()

    def test_default_layout(self):
        self.assertEqual(self.company.account_check_printing_layout, QB_VOUCHER_LAYOUT)
        payment = self._pay_by_check()
        action = payment.with_context(discard_logo_check=True).do_print_checks()
        self.assertEqual(action["report_name"], "horizonforge_accounting.print_check_qb_voucher")

    def test_check_and_stubs(self):
        payment = self._pay_by_check()
        html = self._html(payment)
        self.assertEqual(html.count('class="hf_check_page"'), 1)
        self.assertIn(self.partner_a.name, html)
        self.assertIn("12 Mill Rd", html)
        self.assertIn(payment.check_amount_in_words, html)
        self.assertIn("**", html)
        # Company copy and payee copy.
        self.assertEqual(html.count('class="hf_stub_lines"'), 2)
        self.assertIn("B-0", html)

    def test_long_stub_continues_on_void_pages(self):
        self.company.account_check_printing_multi_stub = True
        payment = self._pay_by_check(count=INV_LINES_PER_STUB + 1, amount=10.0)
        html = self._html(payment)
        self.assertEqual(html.count('class="hf_check_page"'), 2)
        self.assertIn("VOID", html)

    def test_margins_shift_the_layout(self):
        payment = self._pay_by_check()
        self.assertIn("left: 0.000in; top: 0.000in;", self._html(payment))
        self.company.write({"account_check_printing_margin_left": 0.4, "account_check_printing_margin_top": 0.2})
        html = self._html(payment)
        self.assertIn("left: 0.150in; top: -0.050in;", html)

    def _pay_action(self, method_line=None, hf_later=False, **wizard_vals):
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-10-01",
            "invoice_line_ids": [Command.create({"product_id": self.product_a.id, "price_unit": 100.0, "tax_ids": []})],
        })
        bill.action_post()
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=bill.ids, discard_logo_check=True,
        ).create({"payment_method_line_id": (method_line or self.check_method).id, **wizard_vals})
        action = wizard.action_hf_pay_print_later() if hf_later else wizard.action_create_payments()
        return action, bill

    def test_pay_opens_check_numbering(self):
        action, bill = self._pay_action()
        self.assertEqual(action["res_model"], "print.prenumbered.checks")
        self.assertIn(bill.payment_state, ("paid", "in_payment"))

    def test_pay_prints_with_manual_numbering(self):
        self.bank.write({"check_manual_sequencing": True, "check_next_number": "1001"})
        action, _bill = self._pay_action()
        self.assertEqual(action["report_name"], "horizonforge_accounting.print_check_qb_voucher")

    def test_pay_without_layout_opens_payment(self):
        self.company.account_check_printing_layout = "disabled"
        action, bill = self._pay_action()
        self.assertEqual(action["res_model"], "account.payment")
        self.assertIn(bill.payment_state, ("paid", "in_payment"))

    def test_other_methods_unchanged(self):
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        action, _bill = self._pay_action(manual)
        self.assertEqual(action["res_model"], "account.payment")

    def _queue(self):
        self.bank.invalidate_recordset(["kanban_dashboard"])
        return json.loads(self.bank.kanban_dashboard)["hf_checks_to_print"]

    def test_pay_print_later_queues_the_check(self):
        action, bill = self._pay_action(hf_later=True)
        self.assertEqual(action["res_model"], "account.payment")
        payment = self.env["account.payment"].browse(action["res_id"])
        self.assertFalse(payment.is_sent)
        self.assertIn(bill.payment_state, ("paid", "in_payment"))
        self.assertEqual(self._queue(), 1)

    def test_batch_print_from_dashboard(self):
        self._pay_action(hf_later=True)
        self._pay_action(hf_later=True)
        self.assertEqual(self._queue(), 2)
        action = self.bank.action_hf_print_checks()
        self.assertEqual(action["res_model"], "print.prenumbered.checks")
        self.assertEqual(len(action["context"]["payment_ids"]), 2)

    def test_batch_print_manual_numbering_empties_queue(self):
        self.bank.write({"check_manual_sequencing": True, "check_next_number": "2001"})
        self._pay_action(hf_later=True)
        self._pay_action(hf_later=True)
        action = self.bank.with_context(discard_logo_check=True).action_hf_print_checks()
        self.assertEqual(action["report_name"], "horizonforge_accounting.print_check_qb_voucher")
        self.assertEqual(self._queue(), 0)
        with self.assertRaisesRegex(UserError, "no checks to print"):
            self.bank.action_hf_print_checks()

    def test_manual_payments_stay_out_of_the_queue(self):
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        self._pay_action(manual)
        self.assertEqual(self._queue(), 0)

    def _wizard(self, journal=None, preferred=None):
        bill = self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2026-10-01",
            "invoice_line_ids": [Command.create({"product_id": self.product_a.id, "price_unit": 100.0, "tax_ids": []})],
        })
        bill.action_post()
        if preferred:
            bill.preferred_payment_method_line_id = preferred
        vals = {"journal_id": journal.id} if journal else {}
        return self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=bill.ids,
        ).create(vals)

    def test_checks_by_default_from_bank(self):
        wizard = self._wizard(self.bank)
        self.assertEqual(wizard.payment_method_code, "check_printing")

    def test_preferred_method_wins(self):
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        self.assertEqual(self._wizard(self.bank, preferred=manual).payment_method_code, "manual")

    def test_card_journal_keeps_manual(self):
        card = self.env.ref(self.company._hf_xmlid("journal_credit_card"))
        self.assertEqual(self._wizard(card).payment_method_code, "manual")

    def test_switching_method_switches_buttons(self):
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        with Form(self._wizard(self.bank)) as form:
            self.assertEqual(form.payment_method_code, "check_printing")
            form.payment_method_line_id = manual
            self.assertEqual(form.payment_method_code, "manual")

    def test_payments_list_buttons(self):
        arch = self.env["account.payment"].get_view(self.env.ref("account.view_account_payment_tree").id, "list")["arch"]
        self.assertIn('name="print_checks"', arch)
        self.assertNotIn('name="action_post"', arch)
        receipt = self.env.ref("account.action_report_payment_receipt")
        self.assertEqual(receipt.binding_type, "action")

    def test_print_checks_from_list_selection(self):
        self.bank.write({"check_manual_sequencing": True, "check_next_number": "3001"})
        self._pay_action(hf_later=True)
        self._pay_action(hf_later=True)
        payments = self.env["account.payment"].search(self.bank._hf_checks_to_print_domain())
        action = payments.with_context(discard_logo_check=True).print_checks()
        self.assertEqual(action["report_name"], "horizonforge_accounting.print_check_qb_voucher")
        self.assertTrue(all(payments.mapped("is_sent")))

    def test_in_payment_until_the_check_clears(self):
        # account_in_payment answers Paid in tests unless asked for its real state.
        self.env = self.env(context=dict(self.env.context, test_get_invoice_in_payment_state=True))
        self.check_method.payment_account_id = False
        action, bill = self._pay_action(hf_later=True)
        payment = self.env["account.payment"].browse(action["res_id"])
        outstanding = payment._get_outstanding_account("outbound")
        self.assertEqual(payment.outstanding_account_id, outstanding)
        bill.invalidate_recordset(["payment_state"])
        self.assertEqual(bill.payment_state, "in_payment")
        # The check clears: the bank line is matched with the outstanding line.
        cleared = self.env["account.move"].create({
            "move_type": "entry",
            "journal_id": self.bank.id,
            "line_ids": [
                Command.create({"account_id": outstanding.id, "debit": 100.0}),
                Command.create({"account_id": self.bank.default_account_id.id, "credit": 100.0}),
            ],
        })
        cleared.action_post()
        (payment.move_id.line_ids | cleared.line_ids).filtered(lambda l: l.account_id == outstanding).reconcile()
        bill.invalidate_recordset(["payment_state"])
        self.assertEqual(bill.payment_state, "paid")

    def _record_handwritten(self, payments, numbers=None):
        action = payments.action_hf_record_handwritten_checks()
        wizard = self.env["hf.check.handwritten"].browse(action["res_id"])
        if numbers:
            for line, number in zip(wizard.line_ids, numbers):
                line.check_number = number
        wizard.action_record()
        return wizard

    def test_handwritten_checks_leave_the_queue(self):
        self.bank.write({"check_manual_sequencing": True, "check_next_number": "0500"})
        self._pay_action(hf_later=True)
        self._pay_action(hf_later=True)
        payments = self.env["account.payment"].search(self.bank._hf_checks_to_print_domain(), order="date, id")
        action = payments.action_hf_record_handwritten_checks()
        wizard = self.env["hf.check.handwritten"].browse(action["res_id"])
        self.assertEqual(wizard.line_ids.mapped("check_number"), ["0500", "0501"])
        wizard.action_record()
        self.assertEqual(payments.mapped("check_number"), ["0500", "0501"])
        self.assertTrue(all(payments.mapped("is_sent")))
        self.assertEqual(self._queue(), 0)
        # The printer carries on after the handwritten checks.
        self.assertEqual(self.bank.check_next_number, "0502")

    def test_handwritten_number_from_another_book(self):
        self._pay_action(hf_later=True)
        payment = self.env["account.payment"].search(self.bank._hf_checks_to_print_domain())
        self._record_handwritten(payment, ["7001"])
        self.assertEqual(payment.check_number, "7001")
        self.assertEqual(self._queue(), 0)

    def test_handwritten_duplicate_number_refused(self):
        self._pay_action(hf_later=True)
        self._pay_action(hf_later=True)
        payments = self.env["account.payment"].search(self.bank._hf_checks_to_print_domain())
        with self.assertRaises(ValidationError):
            self._record_handwritten(payments, ["900", "900"])

    def test_handwritten_needs_unprinted_checks(self):
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        action, _bill = self._pay_action(manual)
        with self.assertRaisesRegex(UserError, "haven't been printed"):
            self.env["account.payment"].browse(action["res_id"]).action_hf_record_handwritten_checks()

    def test_register_columns(self):
        action, _bill = self._pay_action(hf_later=True)
        check = self.env["account.payment"].browse(action["res_id"])
        self.assertEqual(check.amount_company_currency_signed, -100.0)
        self.assertEqual((check.hf_amount_out, check.hf_amount_in), (100.0, 0.0))
        receipt = self.env["account.payment"].create({
            "payment_type": "inbound",
            "partner_type": "customer",
            "partner_id": self.partner_a.id,
            "amount": 40.0,
            "journal_id": self.bank.id,
        })
        receipt.action_post()
        self.assertEqual((receipt.hf_amount_out, receipt.hf_amount_in), (0.0, 40.0))

    def test_checks_to_print_list_shows_check_amount(self):
        self._pay_action(hf_later=True)
        action = self.bank.action_hf_open_checks_to_print()
        self.assertTrue(action["context"]["hf_checks_to_print"])
        arch = self.env["account.payment"].get_view(self.env.ref("account.view_account_payment_tree").id, "list")["arch"]
        self.assertIn('string="Check Amount"', arch)
        self.assertIn('name="hf_amount_out"', arch)
        self.assertIn('name="hf_amount_in"', arch)

    def _vendor_doc(self, move_type, amount, ref, partner=None):
        move = self.env["account.move"].create({
            "move_type": move_type,
            "partner_id": (partner or self.partner_a).id,
            "invoice_date": "2026-10-01",
            "ref": ref,
            "invoice_line_ids": [Command.create({"product_id": self.product_a.id, "price_unit": amount, "tax_ids": []})],
        })
        move.action_post()
        return move

    def _pay_docs(self, docs):
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=docs.ids,
        ).create({"journal_id": self.bank.id})
        return wizard, wizard._create_payments()

    def test_bills_net_of_vendor_credit(self):
        docs = self._vendor_doc("in_invoice", 300, "B-300") | self._vendor_doc("in_invoice", 200, "B-200") \
            | self._vendor_doc("in_refund", 100, "CR-100")
        wizard, payment = self._pay_docs(docs)
        self.assertTrue(wizard.group_payment)
        self.assertEqual(wizard.payment_method_code, "check_printing")
        self.assertEqual((len(payment), payment.payment_type, payment.amount), (1, "outbound", 400.0))
        self.assertTrue(all(docs.mapped(lambda m: m.currency_id.is_zero(m.amount_residual))))
        lines = payment._check_get_pages()[0]["stub_lines"]
        self.assertEqual(
            [line.get("name") if line.get("header") else (line["number"].split(" - ")[-1], line["amount_paid"]) for line in lines],
            [("B-300", "$\xa0300.00"), ("B-200", "$\xa0200.00"), "Credits", ("CR-100", "$\xa0-100.00")],
        )

    def test_one_check_per_vendor(self):
        other_vendor = self.env["res.partner"].create({"name": "Second Vendor"})
        docs = self._vendor_doc("in_invoice", 300, "A-1") | self._vendor_doc("in_invoice", 80, "B-1", other_vendor)
        _wizard, payments = self._pay_docs(docs)
        self.assertEqual(sorted(payments.mapped("amount")), [80.0, 300.0])
        self.assertEqual(set(payments.mapped("payment_method_line_id.code")), {"check_printing"})

    def test_credit_larger_than_bills_is_not_a_check(self):
        docs = self._vendor_doc("in_invoice", 50, "B-50") | self._vendor_doc("in_refund", 80, "CR-80")
        wizard = self.env["account.payment.register"].with_context(
            active_model="account.move", active_ids=docs.ids,
        ).create({"journal_id": self.bank.id})
        self.assertEqual((wizard.payment_type, wizard.amount), ("inbound", 30.0))
        self.assertNotEqual(wizard.payment_method_code, "check_printing")

    def test_dashboard_has_one_checks_to_print_line(self):
        self._pay_action(hf_later=True)
        self.bank.invalidate_recordset(["kanban_dashboard"])
        data = json.loads(self.bank.kanban_dashboard)
        self.assertEqual((data["num_checks_to_print"], data["hf_checks_to_print"]), (1, 1))
        action = self.bank.action_checks_to_print()
        self.assertEqual(action["domain"], self.bank._hf_checks_to_print_domain())
        self.assertTrue(action["context"]["hf_checks_to_print"])
        arch = self.env["account.journal"].get_view(
            self.env.ref("account.account_journal_dashboard_kanban_view").id, "kanban"
        )["arch"]
        self.assertEqual(arch.count("hf_checks_to_print"), 1)  # only the Print Checks button

    def test_display_status(self):
        self.env = self.env(context=dict(self.env.context, test_get_invoice_in_payment_state=True))
        self.bank.write({"check_manual_sequencing": True, "check_next_number": "4001"})
        action, _bill = self._pay_action(hf_later=True)
        check = self.env["account.payment"].browse(action["res_id"])
        self.assertEqual((check.state, check.hf_status), ("in_process", "to_print"))
        check.with_context(discard_logo_check=True).print_checks()
        self.assertEqual((check.state, check.hf_status, check.check_number), ("in_process", "in_payment", "4001"))
        check.action_validate()
        self.assertEqual(check.hf_status, "paid")
        manual = self.bank.outbound_payment_method_line_ids.filtered(lambda line: line.code == "manual")
        action, _bill = self._pay_action(manual)
        self.assertEqual(self.env["account.payment"].browse(action["res_id"]).hf_status, "in_payment")

    def test_list_status_and_check_number_columns(self):
        arch = self.env["account.payment"].get_view(self.env.ref("account.view_account_payment_tree").id, "list")["arch"]
        self.assertIn('name="hf_status"', arch)
        self.assertIn('string="Check No."', arch)
