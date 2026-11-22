from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    hf_block_quick_create_partner = fields.Boolean(
        string="Block quick-create of contacts",
        config_parameter="horizonforge_ce_custom.block_quick_create_partner",
        help="Typing a new name in a contact field opens the full Create form "
             "instead of saving a bare contact. Users in \"Quick-create Contacts "
             "and Products\" are not affected.",
    )
    hf_block_quick_create_product = fields.Boolean(
        string="Block quick-create of products",
        config_parameter="horizonforge_ce_custom.block_quick_create_product",
        help="Typing a new name in a product field opens the full Create form "
             "instead of saving a bare product. Users in \"Quick-create Contacts "
             "and Products\" are not affected.",
    )
    hf_simple_interface = fields.Boolean(
        string="Simple interface",
        config_parameter="horizonforge_ce_custom.simple_interface",
        help="Users who are not administrators don't see the Discuss, Contacts "
             "and Apps menus, the chat and activity icons, or OdooBot's welcome chat.",
    )

    def set_values(self):
        param = "horizonforge_ce_custom.simple_interface"
        before = self.env["ir.config_parameter"].sudo().get_param(param, "False")
        super().set_values()
        if self.env["ir.config_parameter"].sudo().get_param(param, "False") != before:
            # The menus are cached per user.
            self.env.registry.clear_cache()
