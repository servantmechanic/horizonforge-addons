from odoo import fields, models


class SchoolHomeroom(models.Model):
    _name = "school.homeroom"
    _description = "Homeroom"
    _order = "name"

    name = fields.Char(
        required=True,
        help="The room and its group, for example Lower Room or Grades 1-2.",
    )
    teacher_id = fields.Many2one(
        "res.users",
        string="Teacher",
        domain=lambda self: self.env["school.section"]._teacher_domain(),
        help="Teaches the homeroom's courses, unless a course names its own teacher.",
    )
    capacity = fields.Integer(
        help="Number of students the room holds.",
    )
    grade_level_ids = fields.Many2many(
        "school.grade.level",
        "school_homeroom_grade_level_rel",
        "homeroom_id",
        "grade_level_id",
        string="Grade Levels",
        help="The homeroom's students take the courses of their own grade level.",
    )
    student_ids = fields.One2many(
        "school.student",
        "homeroom_id",
        string="Students",
    )
    student_count = fields.Integer(
        string="Student Count",
        compute="_compute_student_count",
    )
    active = fields.Boolean(default=True)

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "Homeroom names must be unique.",
    )

    def _compute_student_count(self):
        counts = dict(self.env["school.student"]._read_group(
            [("homeroom_id", "in", self.ids)],
            ["homeroom_id"],
            ["__count"],
        ))
        for homeroom in self:
            homeroom.student_count = counts.get(homeroom, 0)
