from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    np_lock_date = fields.Date(
        related="company_id.np_lock_date",
        readonly=False,
    )
    np_default_payment_account_id = fields.Many2one(
        related="company_id.np_default_payment_account_id",
        readonly=False,
    )
