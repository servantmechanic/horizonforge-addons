from odoo import api, models


class AccountPaymentRegister(models.TransientModel):
    _inherit = "account.payment.register"

    @api.depends("can_edit_wizard", "can_group_payments", "payment_method_line_id")
    def _compute_group_payment(self):
        """Group check payments by vendor: one check per vendor, net of their
        credit notes. Core pays each bill separately, and refunds the credits
        as incoming payments."""
        super()._compute_group_payment()
        for wizard in self:
            if wizard.can_group_payments and wizard.payment_method_line_id.code == "check_printing":
                wizard.group_payment = True

    def _compute_payment_method_line_id(self):
        """Pay from a bank account by check unless told otherwise.

        Core takes the journal's first method, Manual Payment. A preferred
        method on the bills (or their vendor) still wins, and credit card
        journals keep Manual.
        """
        super()._compute_payment_method_line_id()
        for wizard in self:
            journal = wizard.journal_id
            if (
                wizard.payment_type != "outbound"
                or journal.type != "bank"
                or journal.default_account_id.account_type == "liability_credit_card"
                or wizard.payment_method_line_id.code != "manual"
                or wizard.line_ids.move_id.preferred_payment_method_line_id
            ):
                continue
            check = journal._get_available_payment_method_lines("outbound").filtered(
                lambda line: line.code == "check_printing"
            )[:1]
            if check:
                wizard.payment_method_line_id = check._origin

    def action_create_payments(self):
        """Paying by check goes straight to printing it, as in QuickBooks.

        Core opens the payment instead, where Print Check is one more click.
        Other payment methods, and checks without a layout set up, keep
        core's behavior, so a missing setting never blocks paying a bill.
        """
        if (
            self.payment_method_line_id.code != "check_printing"
            or self.env.context.get("dont_redirect_to_payments")
            or self.env.context.get("hf_print_later")
        ):
            return super().action_create_payments()
        payment_ids = []
        action = super(AccountPaymentRegister, self.with_context(hf_collect_payment_ids=payment_ids)).action_create_payments()
        payments = self.env["account.payment"].browse(payment_ids).filtered(
            lambda p: p.payment_method_line_id.code == "check_printing" and not p.is_sent
        )
        layout = self.journal_id.bank_check_printing_layout or self.company_id.account_check_printing_layout
        if not payments or not layout or layout == "disabled" or len(payments.journal_id) != 1:
            return action
        return payments.print_checks()

    def action_hf_pay_print_later(self):
        """Record the check payment and leave the check in the print queue.

        The queue is printed later in one batch, from the bank journal's card
        on the Accounting dashboard or Payments > Checks to Print.
        """
        return self.with_context(hf_print_later=True).action_create_payments()

    def _create_payments(self):
        payments = super()._create_payments()
        collected = self.env.context.get("hf_collect_payment_ids")
        if collected is not None:
            collected.extend(payments.ids)
        return payments
