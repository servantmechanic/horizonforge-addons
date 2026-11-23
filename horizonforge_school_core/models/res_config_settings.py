from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    school_principal_name = fields.Char(
        related="company_id.school_principal_name",
        readonly=False,
    )
    school_name_order = fields.Selection(
        related="company_id.school_name_order",
        readonly=False,
    )
    school_current_year_id = fields.Many2one(
        "school.year",
        string="Current School Year",
        compute="_compute_school_current_year_id",
        inverse="_inverse_school_current_year_id",
    )

    def _compute_school_current_year_id(self):
        self.school_current_year_id = self.env["school.year"]._get_current()

    def _inverse_school_current_year_id(self):
        for settings in self:
            if settings.school_current_year_id:
                settings.school_current_year_id.is_current = True
            else:
                self.env["school.year"]._get_current().is_current = False
