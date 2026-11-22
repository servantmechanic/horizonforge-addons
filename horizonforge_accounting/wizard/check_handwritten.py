from odoo import api, fields, models
from odoo.exceptions import UserError


class HfCheckHandwritten(models.TransientModel):
    """Record checks written by hand, so they leave the print queue."""

    _name = "hf.check.handwritten"
    _description = "Record Handwritten Checks"

    line_ids = fields.One2many("hf.check.handwritten.line", "wizard_id", string="Checks")

    @api.model
    def _next_check_number(self, journal):
        """The number the next check would get, as core's printing does."""
        if journal.check_manual_sequencing:
            return journal.check_next_number
        last = self.env["account.payment"].search(
            [("journal_id", "=", journal.id), ("check_number", "!=", False)],
            order="check_number desc",
        ).sorted(lambda p: int(p.check_number))[-1:].check_number
        return f"{int(last) + 1:0{len(last)}}" if last else "1"

    @api.model
    def _prepare_lines(self, payments):
        lines = []
        numbers = {}
        for payment in payments.sorted(lambda p: (p.date, p.id)):
            journal = payment.journal_id
            if journal not in numbers:
                numbers[journal] = self._next_check_number(journal) or "1"
            number = numbers[journal]
            lines.append((0, 0, {"payment_id": payment.id, "check_number": number}))
            numbers[journal] = f"{int(number) + 1:0{len(number)}}"
        return lines

    def action_record(self):
        self.ensure_one()
        if any(not line.check_number for line in self.line_ids):
            raise UserError(self.env._("Enter the number of each check."))
        payments = self.line_ids.payment_id
        payments.filtered(lambda p: p.state == "draft").action_post()
        for line in self.line_ids:
            line.payment_id.write({"check_number": line.check_number, "is_sent": True})
            line.payment_id.message_post(body=self.env._(
                "Check %(number)s written by hand.", number=line.check_number,
            ))
        # Keep the printer's numbering past checks taken from the same book.
        for journal in payments.journal_id.filtered("check_manual_sequencing"):
            used = [int(n) for n in self.line_ids.filtered(lambda l, j=journal: l.payment_id.journal_id == j).mapped("check_number")]
            if max(used) >= int(journal.check_next_number or 0):
                width = len(journal.check_next_number or "")
                journal.check_next_number = f"{max(used) + 1:0{width}}"
        return {"type": "ir.actions.act_window_close"}


class HfCheckHandwrittenLine(models.TransientModel):
    _name = "hf.check.handwritten.line"
    _description = "Handwritten Check"

    wizard_id = fields.Many2one("hf.check.handwritten", required=True, ondelete="cascade")
    payment_id = fields.Many2one("account.payment", required=True, readonly=True)
    partner_id = fields.Many2one(related="payment_id.partner_id", string="Payee")
    date = fields.Date(related="payment_id.date")
    amount = fields.Monetary(related="payment_id.amount")
    currency_id = fields.Many2one(related="payment_id.currency_id")
    journal_id = fields.Many2one(related="payment_id.journal_id")
    check_number = fields.Char(required=True)
