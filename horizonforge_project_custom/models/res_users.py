from odoo import api, models
from odoo.tools import str2bool


class ResUsers(models.Model):
    _inherit = "res.users"

    @api.model
    def _hf_enable_analytic_accounting(self):
        """Same as ticking the Analytic Accounting setting; job costing needs it."""
        analytic_group = self.env.ref("analytic.group_analytic_accounting")
        self.env.ref("base.group_user").sudo().implied_ids |= analytic_group

    def _hf_portal_toggle(self, name):
        """Return whether a horizonforge_project_custom toggle is on."""
        param = f"horizonforge_project_custom.{name}"
        return str2bool(self.env["ir.config_parameter"].sudo().get_param(param, "False"))

    def _hf_portal_orders_hidden(self):
        """Used by the record rules: internal users are never restricted."""
        return self.share and self._hf_portal_toggle("portal_hide_sales_orders")
