from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SchoolAssignmentGenerate(models.TransientModel):
    _name = "school.assignment.generate"
    _description = "Generate Assignments"

    period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        required=True,
        default=lambda self: self._default_period(),
        domain="[('locked', '=', False)]",
    )
    section_ids = fields.Many2many(
        "school.section",
        string="Classes",
        compute="_compute_section_ids",
        store=True,
        readonly=False,
        domain="[('year_id', '=', year_id), ('course_id.assignment_template_ids', '!=', False)]",
        help="Only classes whose course has an assignment schedule.",
    )
    year_id = fields.Many2one(related="period_id.year_id")

    @api.model
    def _default_period(self):
        year = self.env["school.year"]._get_current()
        today = fields.Date.context_today(self)
        periods = year.period_ids.filtered(lambda p: not p.locked)
        return (
            periods.filtered(lambda p: p.date_start <= today <= p.date_end)
            or periods.filtered(lambda p: p.date_start > today)[:1]
            or periods[-1:]
        )

    @api.depends("period_id")
    def _compute_section_ids(self):
        for wizard in self:
            sections = self.env["school.section"]._gradebook_sections().filtered(
                lambda s: s.year_id == wizard.period_id.year_id
                and s.course_id.assignment_template_ids
            )
            user = self.env.user
            own = sections.filtered(lambda s: user in (s.teacher_id | s.co_teacher_ids))
            wizard.section_ids = own or sections

    def action_generate(self):
        self.ensure_one()
        if not self.section_ids:
            raise UserError(_(
                "No class to generate for. Add assignment schedules to the "
                "courses first (Gradebook, Assignment Schedules)."
            ))
        assignments = self.section_ids._generate_assignments(self.period_id)
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if assignments else "info",
                "message": _(
                    "%(count)s assignments created in %(classes)s classes for %(period)s.",
                    count=len(assignments),
                    classes=len(assignments.section_id),
                    period=self.period_id.name,
                ),
                "next": {"type": "ir.actions.act_window_close"},
            },
        }
