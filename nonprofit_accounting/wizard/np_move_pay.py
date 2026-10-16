from odoo import fields, models


class NpMovePay(models.TransientModel):
    _name = "np.move.pay"
    _description = "Pay Bill"

    move_id = fields.Many2one(
        "np.move",
        string="Bill",
        required=True,
        domain=[("move_type", "=", "payment"), ("state", "=", "draft")],
    )
    currency_id = fields.Many2one(related="move_id.currency_id")
    amount_total = fields.Monetary(related="move_id.amount_total")
    paid_date = fields.Date(
        required=True,
        help="Defaults to the bill date. This is the date the payment hits the books.",
    )
    bank_account_id = fields.Many2one(
        "np.account",
        string="Pay From",
        required=True,
        domain=[("account_type", "=", "bank")],
    )
    check_number = fields.Char(string="Check #")

    def action_pay(self):
        self.ensure_one()
        self.move_id.write({
            "date": self.paid_date,
            "bank_account_id": self.bank_account_id.id,
            "check_number": self.check_number,
        })
        self.move_id.action_post()
        return {"type": "ir.actions.act_window_close"}
