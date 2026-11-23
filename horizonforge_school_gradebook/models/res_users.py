from odoo import api, fields, models

ENTER_DIRECTIONS = [
    ("down", "Down to the next student"),
    ("right", "Right to the next assignment"),
]


class ResUsers(models.Model):
    _inherit = "res.users"

    school_enter_direction = fields.Selection(
        ENTER_DIRECTIONS,
        string="Gradebook: Enter Moves",
        default="down",
        required=True,
    )

    @api.model_create_multi
    def create(self, vals_list):
        """New users start with the school's default."""
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
            vals.setdefault("school_enter_direction", company.school_enter_direction)
        return super().create(vals_list)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["school_enter_direction"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["school_enter_direction"]
