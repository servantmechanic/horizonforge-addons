from odoo import api, fields, models

from .school_assignment import ENTRY_MODES


class ResCompany(models.Model):
    _inherit = "res.company"

    school_entry_mode = fields.Selection(
        ENTRY_MODES,
        string="Entry Mode",
        default="percent",
        required=True,
        help="What teachers type in the gradebook, unless a class or an "
        "assignment says otherwise.",
    )
    school_missing_work = fields.Selection(
        [
            ("zero", "Counts as 0"),
            ("skip", "Left out until entered"),
        ],
        string="Missing Work",
        default="zero",
        required=True,
        help="How a score marked missing (M) counts in the averages. "
        "Excused scores and empty cells never count.",
    )
    school_grade_decimals = fields.Integer(
        string="Grade Decimals",
        default=0,
        help="Decimals of the period and year grades. 0 rounds to a whole "
        "number, half up: 92.5 becomes 93. The letter is looked up on the "
        "rounded grade.",
    )
    school_display_decimals = fields.Integer(
        string="Average Decimals",
        default=1,
        help="Decimals shown for category and class averages.",
    )
    school_year_grade = fields.Selection(
        [
            ("average", "Average of the period grades"),
            ("cumulative", "Cumulative over all the year's scores"),
        ],
        string="Year Grade",
        default="average",
        required=True,
    )
    school_weight_scheme_id = fields.Many2one(
        "school.weight.scheme",
        string="Weight Scheme",
        help="Used by every course and class without its own weight scheme.",
    )
    school_grading_scale_id = fields.Many2one(
        "school.grading.scale",
        string="Grading Scale",
        help="Used by every grade level and course without its own scale.",
    )

    _school_decimals_range = models.Constraint(
        "CHECK(school_grade_decimals BETWEEN 0 AND 2 AND school_display_decimals BETWEEN 0 AND 2)",
        "Grade and average decimals must be between 0 and 2.",
    )

    @api.model
    def _school_gradebook_set_defaults(self):
        """Give companies without them the shipped weight scheme and scale."""
        scheme = self.env.ref(
            "horizonforge_school_gradebook.weight_scheme_standard", raise_if_not_found=False
        )
        scale = self.env.ref(
            "horizonforge_school_gradebook.grading_scale_letters", raise_if_not_found=False
        )
        for company in self.search([]):
            if scheme and not company.school_weight_scheme_id:
                company.school_weight_scheme_id = scheme
            if scale and not company.school_grading_scale_id:
                company.school_grading_scale_id = scale
