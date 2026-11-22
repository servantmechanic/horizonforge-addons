from odoo import models


class IrHttp(models.AbstractModel):
    _inherit = "ir.http"

    def session_info(self):
        info = super().session_info()
        if self.env.user._is_internal():
            info["hf_simple_interface"] = self.env.user._hf_simple_interface()
        return info
