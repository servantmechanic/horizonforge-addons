from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    school_principal_name = fields.Char(
        string="Principal",
        help="Printed in the header of school reports, with the company "
        "name, address and logo.",
    )
