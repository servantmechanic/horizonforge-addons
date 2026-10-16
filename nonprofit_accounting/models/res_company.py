from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    np_lock_date = fields.Date(
        string="Lock Date",
        help="Entries dated on or before this date can't be posted, "
        "reset to draft or changed.",
    )
    np_default_payment_account_id = fields.Many2one(
        "np.account",
        string="Default Payment Account",
        domain=[("account_type", "=", "bank")],
        help="Used for Pay From when paying a bill, unless the vendor was "
        "last paid from a different account.",
    )
