from odoo import api, fields, models


class MailFollowers(models.Model):
    _inherit = "mail.followers"

    hf_auto_followed = fields.Boolean(
        string="Added by auto-follow",
        help="The follower was added by following the project, not by hand. "
             "Unfollowing the project removes it.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        if self.env.context.get("hf_auto_follow"):
            vals_list = [dict(vals, hf_auto_followed=True) for vals in vals_list]
        return super().create(vals_list)
