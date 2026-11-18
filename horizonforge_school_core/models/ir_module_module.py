from odoo import api, models, release


class IrModuleModule(models.Model):
    _inherit = "ir.module.module"

    @api.model
    def _school_version(self):
        """The installed version of the school addons, without the Odoo
        series: "0.7.0" for 19.0.0.7.0. All school modules share it; see
        CHANGELOG.md."""
        module = self.sudo().search([("name", "=", "horizonforge_school_core")], limit=1)
        return (module.latest_version or "").removeprefix(release.series + ".")
