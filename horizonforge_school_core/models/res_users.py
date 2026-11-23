from odoo import api, fields, models

NAME_ORDERS = [
    ("last_first", "Last name, First name"),
    ("first_last", "First name Last name"),
]


class ResUsers(models.Model):
    _inherit = "res.users"

    school_name_order = fields.Selection(
        NAME_ORDERS,
        string="Student Names",
        default="last_first",
        required=True,
        help="How students are shown and sorted in the gradebook and attendance grids.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """New users start with the school's default."""
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
            vals.setdefault("school_name_order", company.school_name_order)
        return super().create(vals_list)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["school_name_order"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["school_name_order"]
