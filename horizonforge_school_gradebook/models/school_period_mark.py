from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolPeriodMark(models.Model):
    """A student's report card comment in one class for a grading period."""

    _name = "school.period.mark"
    _description = "Report Card Comment"
    _order = "period_id, section_id, student_id"

    section_id = fields.Many2one(
        "school.section",
        string="Class",
        required=True,
        ondelete="cascade",
        index=True,
    )
    student_id = fields.Many2one(
        "school.student",
        string="Student",
        required=True,
        ondelete="restrict",
        index=True,
    )
    period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        required=True,
        ondelete="restrict",
        index=True,
    )
    grading_type = fields.Selection(related="section_id.grading_type")
    grade_level_ids = fields.Many2many(
        related="section_id.course_id.grade_level_ids",
        string="Grade Levels",
        store=True,
    )
    comment = fields.Text(
        help="Prints on the report card, under the class's name.",
    )

    _section_student_period_unique = models.Constraint(
        "UNIQUE(section_id, student_id, period_id)",
        "A student has one report card comment per class and grading period.",
    )

    @api.depends("student_id", "section_id", "period_id")
    def _compute_display_name(self):
        for mark in self:
            mark.display_name = (
                f"{mark.student_id.display_name} - {mark.section_id.display_name} - {mark.period_id.name}"
            )

    def _check_unlocked(self):
        if self.env.su or self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            return
        locked = self.period_id.filtered("locked")
        if locked:
            raise ValidationError(_(
                "%(period)s is locked. Ask the principal to change its grades.",
                period=locked[0].display_name,
            ))

    @api.model_create_multi
    def create(self, vals_list):
        marks = super().create(vals_list)
        if any(mark.comment for mark in marks):
            marks._check_unlocked()
        return marks

    def write(self, vals):
        self._check_unlocked()
        return super().write(vals)

    def unlink(self):
        self.filtered("comment")._check_unlocked()
        return super().unlink()

    @api.model
    def _ensure_rows(self, sections):
        """One row per student for every grading period that has started
        and isn't locked, so the teacher only fills them in."""
        today = fields.Date.context_today(self)
        vals_list = []
        for section in sections:
            existing = {
                (mark.student_id.id, mark.period_id.id)
                for mark in self.search([("section_id", "=", section.id)])
            }
            periods = section.year_id.period_ids.filtered(
                lambda p: not p.locked and p.date_start <= today
            ) or section.year_id.period_ids.filtered(lambda p: not p.locked)[:1]
            for period in periods:
                for enrollment in section.enrollment_ids:
                    if enrollment.date_start > period.date_end or (
                        enrollment.date_end and enrollment.date_end < period.date_start
                    ):
                        continue
                    key = (enrollment.student_id.id, period.id)
                    if key not in existing:
                        existing.add(key)
                        vals_list.append({
                            "section_id": section.id,
                            "student_id": enrollment.student_id.id,
                            "period_id": period.id,
                        })
        # The rows are only placeholders: creating them needs no rights of
        # its own beyond seeing the class.
        sections.check_access("read")
        return self.sudo().create(vals_list)

    @api.model
    def action_open_marks(self, sections=None):
        """Open the list for some classes (default: the user's own in the
        current year), on the current grading period."""
        if sections is None:
            user = self.env.user
            domain = [("year_id.is_current", "=", True)]
            if not user.has_group("horizonforge_school_core.group_school_admin"):
                domain += self.env["school.section"]._my_classes_domain(user)
            sections = self.env["school.section"].search(domain)
            from_menu = True
        else:
            from_menu = False
        self._ensure_rows(sections)
        today = fields.Date.context_today(self)
        periods = sections.year_id.period_ids
        current = (
            periods.filtered(lambda p: p.date_start <= today <= p.date_end)
            or periods.filtered(lambda p: p.date_end < today)[-1:]
            or periods[:1]
        )
        if from_menu:
            # Teachers start on their own classes; nothing is fixed, so any
            # class or period can be picked again after clearing a filter.
            action = self.env["school.period"]._school_list_action(
                "horizonforge_school_gradebook.school_period_mark_action", "my_classes")
            action["context"]["search_default_current_year"] = 1
        else:
            action = self.env["ir.actions.act_window"]._for_xml_id(
                "horizonforge_school_gradebook.school_period_mark_action"
            )
            action["domain"] = [("section_id", "in", sections.ids)]
            action["context"] = {}
        if current:
            action["context"]["searchpanel_default_period_id"] = current[:1].id
        action["context"]["search_default_group_section"] = 0 if len(sections) == 1 else 1
        return action
