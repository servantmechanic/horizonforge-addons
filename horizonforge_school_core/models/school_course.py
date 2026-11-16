from odoo import fields, models


class SchoolCourse(models.Model):
    _name = "school.course"
    _description = "Course"
    _order = "sequence, name"
    _rec_names_search = ["name", "code"]

    name = fields.Char(
        required=True,
        help="The subject as taught to one group, for example Math 5.",
    )
    code = fields.Char(
        help="Short code, for example MA5.",
    )
    sequence = fields.Integer(
        default=10,
        help="Order of the subjects on report cards.",
    )
    grade_level_ids = fields.Many2many(
        "school.grade.level",
        string="Grade Levels",
        help="Grade levels that take this course.",
    )
    teacher_id = fields.Many2one(
        "res.users",
        string="Teacher",
        domain=lambda self: self.env["school.section"]._teacher_domain(),
        help="Set only when someone other than the homeroom teacher teaches "
        "this course, for example a music teacher. New classes of the "
        "course get this teacher.",
    )
    active = fields.Boolean(default=True)
    section_ids = fields.One2many(
        "school.section",
        "course_id",
        string="Classes",
    )

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Course codes must be unique.",
    )
