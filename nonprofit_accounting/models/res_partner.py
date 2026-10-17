from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    np_income_account_id = fields.Many2one(
        "np.account",
        string="Default Income Account",
        domain=[("account_type", "=", "income")],
        help="Pre-filled on new deposit lines when this contact is Received From.",
    )
    np_expense_account_id = fields.Many2one(
        "np.account",
        string="Default Expense Account",
        domain=[("account_type", "=", "expense")],
        help="Pre-filled on new bill lines when this contact is Paid To.",
    )
