from odoo import fields, models

from .res_users import NAME_ORDERS


class ResCompany(models.Model):
    _inherit = "res.company"

    school_principal_name = fields.Char(
        string="Principal",
        help="Printed in the header of school reports, with the company "
        "name, address and logo.",
    )
    school_name_order = fields.Selection(
        NAME_ORDERS,
        string="Student Names",
        default="last_first",
        required=True,
        help="The default for new users. Each teacher can change their own "
        "in My Preferences.",
    )
