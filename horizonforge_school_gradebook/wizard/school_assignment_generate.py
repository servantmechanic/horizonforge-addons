from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SchoolAssignmentGenerate(models.TransientModel):
    _name = "school.assignment.generate"
    _description = "Fill Ahead"

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
        domain="[('year_id', '=', year_id)]",
        help="Classes with something to fill from: an assignment schedule "
        "(or, with the planner, a pacing guide).",
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
                lambda s: s.year_id == wizard.period_id.year_id and s._can_fill_ahead()
            )
            user = self.env.user
            own = sections.filtered(lambda s: s._is_my_class(user))
            wizard.section_ids = own or sections

    def action_generate(self):
        self.ensure_one()
        sections = self.section_ids.filtered(lambda s: s._can_fill_ahead())
        if not sections:
            raise UserError(_(
                "No class to fill. Give the courses an assignment schedule "
                "(Assignment Schedules) or a pacing guide first."
            ))
        assignments = self.env["school.assignment"]
        for section in sections:
            assignments |= section._fill_ahead(self.period_id)
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
