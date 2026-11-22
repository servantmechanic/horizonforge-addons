from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        if self.env.user.has_group("horizonforge_school_core.group_school_teacher"):
            info["school_version"] = self.env["ir.module.module"]._school_version()
        return info
