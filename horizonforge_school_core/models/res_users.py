from odoo import fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    school_name_order = fields.Selection(
        [
            ("last_first", "Last name, First name"),
            ("first_last", "First name Last name"),
        ],
        string="Student Names",
        default="last_first",
        required=True,
        help="How students are shown and sorted in the gradebook and attendance grids.",
    )

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["school_name_order"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["school_name_order"]
