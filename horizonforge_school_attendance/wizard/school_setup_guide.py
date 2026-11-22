from odoo import fields, models


class SchoolSetupGuide(models.TransientModel):
    _inherit = "school.setup.guide"

    attendance_code_count = fields.Integer(compute="_compute_counts")

    def _compute_counts(self):
        super()._compute_counts()
        self.attendance_code_count = self.env["school.attendance.code"].search_count([])

    def action_attendance_codes(self):
        return self._open("horizonforge_school_attendance.school_attendance_code_action")
