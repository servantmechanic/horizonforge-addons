from odoo import fields, models

from .school_assignment import ENTRY_MODES


class SchoolCourse(models.Model):
    _inherit = "school.course"

    grading_type = fields.Selection(
        [
            ("percent", "Scores and percent"),
            ("letter", "Letters"),
            ("comment", "Comment only"),
        ],
        string="Graded By",
        default="percent",
        required=True,
        help="Scores and percent: graded in the gradebook, the grade shown "
        "as a percent and a letter. Letters: graded in the gradebook too, "
        "assignments typed as letters by default (PE, art), and the grade "
        "shown as a letter only. Comment only: no grades, a report card "
        "comment per grading period.",
    )
    entry_mode = fields.Selection(
        ENTRY_MODES,
        help="What teachers type in the gradebook for this course. Leave "
        "empty to use the school's entry mode.",
    )
    weight_scheme_id = fields.Many2one(
        "school.weight.scheme",
        string="Weight Scheme",
        ondelete="restrict",
        help="Leave empty to use the school's weight scheme.",
    )
    grading_scale_id = fields.Many2one(
        "school.grading.scale",
        string="Grading Scale",
        ondelete="restrict",
        help="Leave empty to use the grade level's or the school's scale.",
    )
    assignment_template_ids = fields.One2many(
        "school.assignment.template",
        "course_id",
        string="Assignment Schedule",
        copy=True,
    )


class SchoolGradeLevel(models.Model):
    _inherit = "school.grade.level"

    grading_scale_id = fields.Many2one(
        "school.grading.scale",
        string="Grading Scale",
        ondelete="restrict",
        help="For grade levels with their own scale, for example E/S/N/U in "
        "the lower grades. Leave empty to use the school's scale.",
    )


class SchoolYearSetup(models.TransientModel):
    _inherit = "school.year.setup"

    def _copy_section_vals(self, section, year):
        vals = super()._copy_section_vals(section, year)
        vals["entry_mode"] = section.entry_mode
        vals["weight_scheme_id"] = section.weight_scheme_id.id
        return vals
