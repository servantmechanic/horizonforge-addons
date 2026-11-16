from odoo import fields, models


class SchoolGradeLevel(models.Model):
    _name = "school.grade.level"
    _description = "Grade Level"
    _order = "sequence, id"

    name = fields.Char(
        required=True,
        help="For example Kindergarten or Grade 5.",
    )
    sequence = fields.Integer(
        default=10,
        help="Order of the grade levels, lowest grade first.",
    )
    student_ids = fields.One2many(
        "school.student",
        "grade_level_id",
        string="Students",
    )
    student_count = fields.Integer(compute="_compute_student_count")
    homeroom_ids = fields.Many2many(
        "school.homeroom",
        "school_homeroom_grade_level_rel",
        "grade_level_id",
        "homeroom_id",
        string="Homerooms",
    )

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Grade level names must be unique.",
    )

    def _compute_student_count(self):
        counts = dict(self.env["school.student"]._read_group(
            [("grade_level_id", "in", self.ids)],
            ["grade_level_id"],
            ["__count"],
        ))
        for level in self:
            level.student_count = counts.get(level, 0)
