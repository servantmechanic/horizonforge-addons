from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    school_enter_direction = fields.Selection(
        [
            ("down", "Down to the next student"),
            ("right", "Right to the next assignment"),
        ],
        string="Gradebook: Enter Moves",
        default="down",
        required=True,
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["school_enter_direction"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["school_enter_direction"]
