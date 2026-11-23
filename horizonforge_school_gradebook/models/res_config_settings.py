from odoo import fields, models


class SchoolGradebookSettingsMixin(models.AbstractModel):
    """The gradebook's school settings, shared by Odoo's Settings (for the
    system administrator) and School Settings (for the principal)."""

    _name = "school.gradebook.settings.mixin"
    _description = "Gradebook Settings"

    company_id = fields.Many2one("res.company")

    school_card_motto = fields.Text(
        related="company_id.school_card_motto",
        readonly=False,
    )
    school_card_letter = fields.Text(
        related="company_id.school_card_letter",
        readonly=False,
    )
    school_card_letter_signature = fields.Char(
        related="company_id.school_card_letter_signature",
        readonly=False,
    )
    school_conduct_traits = fields.Text(
        related="company_id.school_conduct_traits",
        readonly=False,
    )

    school_enter_direction = fields.Selection(
        related="company_id.school_enter_direction",
        readonly=False,
    )
    school_tab_adds_column = fields.Boolean(
        related="company_id.school_tab_adds_column",
        readonly=False,
    )
    school_cell_letters = fields.Boolean(
        related="company_id.school_cell_letters",
        readonly=False,
    )
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


class ResConfigSettings(models.TransientModel):
    _name = "res.config.settings"
    _inherit = ["res.config.settings", "school.gradebook.settings.mixin"]


class SchoolSettings(models.TransientModel):
    _name = "school.settings"
    _inherit = ["school.settings", "school.gradebook.settings.mixin"]
