from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.tools.misc import format_date, formatLang

from odoo.addons.account_check_printing.models.account_payment import INV_LINES_PER_STUB


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # Register-style columns for payment lists: both positive, each with its
    # own total, instead of core's signed Amount.
    hf_amount_out = fields.Monetary(
        string="Paid Out",
        currency_field="company_currency_id",
        compute="_compute_hf_amount_in_out",
        store=True,
    )
    hf_amount_in = fields.Monetary(
        string="Received",
        currency_field="company_currency_id",
        compute="_compute_hf_amount_in_out",
        store=True,
    )

    # A display status for payment lists. The real state stays core's (Draft,
    # In Process, Paid...), which reconciliation depends on; this one splits
    # In Process into To Print and In Payment, like the bill's status.
    hf_status = fields.Selection(
        [
            ("draft", "Draft"),
            ("to_print", "To Print"),
            ("in_payment", "In Payment"),
            ("paid", "Paid"),
            ("canceled", "Cancelled"),
            ("rejected", "Rejected"),
        ],
        string="Status",
        compute="_compute_hf_status",
        store=True,
    )

    @api.depends("state", "is_sent", "payment_method_line_id.code")
    def _compute_hf_status(self):
        for pay in self:
            if pay.state == "in_process":
                unprinted = pay.payment_method_line_id.code == "check_printing" and not pay.is_sent
                pay.hf_status = "to_print" if unprinted else "in_payment"
            else:
                pay.hf_status = pay.state or "draft"

    @api.depends("amount_company_currency_signed")
    def _compute_hf_amount_in_out(self):
        for pay in self:
            signed = pay.amount_company_currency_signed
            pay.hf_amount_out = -signed if signed < 0 else 0.0
            pay.hf_amount_in = signed if signed > 0 else 0.0

    @api.depends("payment_method_line_id")
    def _compute_outstanding_account_id(self):
        """Keep bank payments on Outstanding Payments / Receipts.

        Community core forces these accounts only while it reports invoices
        as Paid; account_in_payment switches that to In Payment, after which
        a method without an account would post no journal entry at all.
        """
        super()._compute_outstanding_account_id()
        for pay in self:
            if not pay.outstanding_account_id and pay.journal_id.type in ("bank", "credit") and pay.payment_type:
                pay.outstanding_account_id = pay._get_outstanding_account(pay.payment_type)

    def action_hf_record_handwritten_checks(self):
        """Ask for the numbers of checks written by hand, then take them out
        of the print queue."""
        checks = self.filtered(lambda p: p.payment_method_line_id.code == "check_printing" and not p.is_sent
                               and p.state in ("draft", "in_process", "paid"))
        if not checks:
            raise UserError(self.env._(
                "Select check payments that haven't been printed yet. Printed checks already "
                "have a number."
            ))
        Wizard = self.env["hf.check.handwritten"]
        wizard = Wizard.create({"line_ids": Wizard._prepare_lines(checks)})
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Record Handwritten Checks"),
            "res_model": Wizard._name,
            "res_id": wizard.id,
            "view_mode": "form",
            "target": "new",
        }

    def _check_make_stub_pages(self):
        """Vendor check stubs list the bills at what they settle and the vendor
        credits used, so the lines add up to the check.

        Core leaves vendor credit notes off the stub, and when a check pays
        bills net of a credit, shows a bill as partly paid with no reason.
        """
        self.ensure_one()
        if self.partner_type != "supplier" or self.payment_type != "outbound" or not self.move_id:
            return super()._check_make_stub_pages()
        payable = self.move_id.line_ids.filtered(lambda l: l.account_id.account_type == "liability_payable")
        partials = payable.matched_debit_ids | payable.matched_credit_ids
        bill_lines = (partials.debit_move_id | partials.credit_move_id).filtered(
            lambda l: l.move_id.move_type in ("in_invoice", "in_receipt")
        )
        if not bill_lines:
            return super()._check_make_stub_pages()
        bills = bill_lines.move_id
        # Vendor credits applied to these bills.
        bill_partials = bill_lines.matched_debit_ids | bill_lines.matched_credit_ids
        credit_lines = (bill_partials.debit_move_id | bill_partials.credit_move_id).filtered(
            lambda l: l.move_id.move_type == "in_refund"
        )
        credit_partials = bill_partials.filtered(
            lambda p: p.debit_move_id in credit_lines or p.credit_move_id in credit_lines
        )

        def money(amount, currency):
            return formatLang(self.env, amount, currency_obj=currency)

        def line(move, paid, sign):
            residual = move.amount_residual
            return {
                "due_date": format_date(self.env, move.invoice_date_due),
                "number": " - ".join([move.name or "/", move.ref] if move.ref else [move.name or "/"]),
                "amount_total": money(sign * move.amount_total, move.currency_id),
                "amount_residual": "-" if move.currency_id.is_zero(residual) else money(sign * residual, move.currency_id),
                "amount_paid": money(sign * paid, self.currency_id),
                "currency": move.currency_id,
            }

        stub_lines = []
        for bill in bills.sorted(lambda m: (m.invoice_date_due or m.date, m.id)):
            paid = sum(
                p.amount for p in (partials | credit_partials)
                if bill in (p.debit_move_id.move_id | p.credit_move_id.move_id)
            )
            stub_lines.append(line(bill, paid, 1))
        credits = credit_lines.move_id
        if credits:
            stub_lines.append({"header": True, "name": self.env._("Credits")})
            for credit in credits.sorted(lambda m: (m.invoice_date or m.date, m.id)):
                used = sum(
                    p.amount for p in credit_partials
                    if credit in (p.debit_move_id.move_id | p.credit_move_id.move_id)
                )
                stub_lines.append(line(credit, used, -1))
        if not self.company_id.account_check_printing_multi_stub:
            limit = INV_LINES_PER_STUB - 1 if len(stub_lines) > INV_LINES_PER_STUB else INV_LINES_PER_STUB
            return [stub_lines[:limit]]
        return [stub_lines[i:i + INV_LINES_PER_STUB] for i in range(0, len(stub_lines), INV_LINES_PER_STUB)]
