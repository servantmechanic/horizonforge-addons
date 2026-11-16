from odoo import fields, models


class SchoolScoreCategory(models.Model):
    _name = "school.score.category"
    _description = "Score Category"
    _order = "sequence, id"

    name = fields.Char(
        required=True,
        help="For example Lesson/Homework or Test.",
    )
    code = fields.Char(
        required=True,
        help="Short code shown in the gradebook column header, for example HW.",
    )
    color = fields.Char(
        default="#4c6ef5",
        help="Color of the code in the gradebook.",
    )
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Score category codes must be unique.",
    )
