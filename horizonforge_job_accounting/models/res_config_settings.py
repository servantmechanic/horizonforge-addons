from odoo import api, fields, models
from odoo.exceptions import ValidationError

from .hf_job_profit_line import BURDEN_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hf_labor_burden_pct = fields.Float(
        string="Labor Burden (%)",
        config_parameter=BURDEN_PARAM,
        help="Added to wage cost in job profitability, for payroll taxes, "
             "workers' compensation and benefits. 0 uses wages only.",
    )

    @api.constrains("hf_labor_burden_pct")
    def _check_hf_labor_burden_pct(self):
        for settings in self:
            if settings.hf_labor_burden_pct < 0:
                raise ValidationError(self.env._("The labor burden can't be negative."))
