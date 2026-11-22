from odoo import api, models

# Apps that the simple interface shows to administrators only. Missing
# modules (no Contacts app, say) are skipped.
SIMPLE_INTERFACE_HIDDEN_MENUS = (
    "mail.menu_root_discuss",
    "contacts.menu_contacts",
    "base.menu_management",
)


class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    def _hf_hidden_menu_ids(self):
        if not self.env.user._hf_simple_interface():
            return []
        ids = []
        for xmlid in SIMPLE_INTERFACE_HIDDEN_MENUS:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                ids.append(menu.id)
        return ids

    def _load_menus_blacklist(self):
        return super()._load_menus_blacklist() + self._hf_hidden_menu_ids()

    @api.model
    def get_user_roots(self):
        hidden = self._hf_hidden_menu_ids()
        return super().get_user_roots().filtered(lambda m: m.id not in hidden)
