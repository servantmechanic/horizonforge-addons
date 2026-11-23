from odoo import _, fields, models


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
        copy=False,
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

    def copy_data(self, default=None):
        """Duplicate Math 2 into Math 2 (copy), to rename Math 3: the grade
        levels and teacher come along, the classes and the code don't."""
        vals_list = super().copy_data(default=default)
        if "name" not in (default or {}):
            for course, vals in zip(self, vals_list):
                vals["name"] = _("%s (copy)", course.name)
        return vals_list
