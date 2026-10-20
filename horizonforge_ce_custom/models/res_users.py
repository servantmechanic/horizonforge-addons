from odoo import models
from odoo.tools import str2bool

# Model -> ir.config_parameter key that turns quick-create off for it.
QUICK_CREATE_PARAMS = {
    "res.partner": "horizonforge_ce_custom.block_quick_create_partner",
    "product.product": "horizonforge_ce_custom.block_quick_create_product",
    "product.template": "horizonforge_ce_custom.block_quick_create_product",
}


class ResUsers(models.Model):
    _inherit = "res.users"

    def _hf_quick_create_blocked(self, model_name):
        """True if this user may not quick-create (name_create) a record of
        ``model_name`` from a many2one field."""
        self.ensure_one()
        param = QUICK_CREATE_PARAMS.get(model_name)
        if not param or self.has_group("horizonforge_ce_custom.group_quick_create"):
            return False
        return str2bool(self.env["ir.config_parameter"].sudo().get_param(param, "False"))
