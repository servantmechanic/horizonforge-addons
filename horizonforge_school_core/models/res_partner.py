from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    is_patron = fields.Boolean(
        string="Patron",
        help="A family contact for one or more students: parent, guardian "
        "or other responsible adult.",
    )
    student_ids = fields.Many2many(
        "school.student",
        "school_student_patron_rel",
        "partner_id",
        "student_id",
        string="Students",
        help="Students this contact is a patron of.",
    )
    relationship = fields.Selection(
        [
            ("mother", "Mother"),
            ("father", "Father"),
            ("guardian", "Guardian"),
            ("grandparent", "Grandparent"),
            ("other", "Other"),
        ],
        string="Relationship",
        help="How this patron is related to their students.",
    )
