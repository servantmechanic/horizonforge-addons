from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    school_entry_mode = fields.Selection(
        related="company_id.school_entry_mode",
        readonly=False,
        required=True,
    )
    school_missing_work = fields.Selection(
        related="company_id.school_missing_work",
        readonly=False,
        required=True,
    )
    school_grade_decimals = fields.Integer(
        related="company_id.school_grade_decimals",
        readonly=False,
    )
    school_display_decimals = fields.Integer(
        related="company_id.school_display_decimals",
        readonly=False,
    )
    school_year_grade = fields.Selection(
        related="company_id.school_year_grade",
        readonly=False,
        required=True,
    )
    school_weight_scheme_id = fields.Many2one(
        related="company_id.school_weight_scheme_id",
        readonly=False,
    )
    school_grading_scale_id = fields.Many2one(
        related="company_id.school_grading_scale_id",
        readonly=False,
    )
