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

    def _hf_simple_interface(self):
        """True if the simple interface is on and this user is not an
        administrator: no Discuss, Contacts or Apps, no chat or activity
        icons, no OdooBot onboarding."""
        self.ensure_one()
        if self.has_group("base.group_system"):
            return False
        return str2bool(self.env["ir.config_parameter"].sudo().get_param(
            "horizonforge_ce_custom.simple_interface", "False"))

    def _on_webclient_bootstrap(self):
        # Before super: OdooBot (mail_bot) starts its onboarding chat on the
        # first login while odoobot_state is unset.
        if ("odoobot_state" in self._fields and self._is_internal()
                and self.odoobot_state in (False, "not_initialized")
                and self._hf_simple_interface()):
            self.sudo().odoobot_state = "disabled"
        return super()._on_webclient_bootstrap()
