from odoo import fields, models


class SchoolSetupGuide(models.TransientModel):
    _inherit = "school.setup.guide"

    template_count = fields.Integer(compute="_compute_counts")
    assignment_count = fields.Integer(compute="_compute_counts")

    def _compute_counts(self):
        super()._compute_counts()
        for guide in self:
            guide.template_count = self.env["school.assignment.template"].search_count([])
            guide.assignment_count = self.env["school.assignment"].search_count(
                [("section_id.year_id", "=", guide.year_id.id)]
            ) if guide.year_id else 0

    def action_grading_settings(self):
        return self._open("horizonforge_school_core.school_settings_form_action")

    def action_weight_schemes(self):
        return self._open("horizonforge_school_gradebook.school_weight_scheme_action")

    def action_grading_scales(self):
        return self._open("horizonforge_school_gradebook.school_grading_scale_action")

    def action_templates(self):
        return self._open("horizonforge_school_gradebook.school_assignment_template_action")

    def action_generate_assignments(self):
        return self._open("horizonforge_school_gradebook.school_assignment_generate_action")

    def action_assignments(self):
        return self._open("horizonforge_school_gradebook.school_assignment_action")
