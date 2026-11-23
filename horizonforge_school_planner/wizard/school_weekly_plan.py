from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools import format_date


class SchoolWeeklyPlan(models.TransientModel):
    """Prints a week of lessons: a page per teacher, the days across and
    the classes down, each day's planned items with their notes."""

    _name = "school.weekly.plan"
    _description = "Weekly Plan"

    week_date = fields.Date(
        string="Week Of",
        required=True,
        default=lambda self: self._default_week_date(),
        help="Any day of the week to print: it prints Monday to Friday.",
    )
    teacher_ids = fields.Many2many(
        "res.users",
        string="Teachers",
        default=lambda self: self.env.user,
        domain=lambda self: self.env["school.section"]._teacher_domain(),
        help="A page per teacher, for their classes with a pacing guide.",
    )
    weeks = fields.Integer(
        string="Weeks",
        default=1,
        help="Print this many weeks, from the week chosen.",
    )

    @api.model
    def _default_week_date(self):
        """This week, or next week from Friday afternoon on: plans are
        printed ahead."""
        today = fields.Date.context_today(self)
        return today + timedelta(days=7) if today.weekday() >= 5 else today

    @api.model
    def _monday(self, day):
        return day - timedelta(days=day.weekday())

    def _get_pages(self):
        """A page per teacher and week: ``{"teacher", "days": [{"date",
        "label", "entries"}], "rows": [{"section", "cells": [[item]]}]}``."""
        self.ensure_one()
        if not 1 <= self.weeks <= 12:
            raise UserError(_("Print 1 to 12 weeks."))
        Section = self.env["school.section"]
        Day = self.env["school.calendar.day"]
        pages = []
        teachers = self.teacher_ids or self.env.user
        for teacher in teachers:
            sections = Section.search([
                ("year_id.is_current", "=", True), ("course_id.pacing_item_ids", "!=", False),
                "|", ("teacher_id", "=", teacher.id), ("co_teacher_ids", "in", teacher.id),
            ]).sorted(lambda s: (
                s.course_id.pacing_guide_id.sequence, s.course_id.sequence, s.course_id.name or "", s.id,
            ))
            sections._replan()
            for week in range(self.weeks):
                monday = self._monday(self.week_date) + timedelta(weeks=week)
                dates = [monday + timedelta(days=i) for i in range(5)]
                entries = Day.search(
                    [("date_start", "<=", dates[-1]), ("date_end", ">=", dates[0])]
                    + Day._for_me_domain(teacher)
                )
                days = [{
                    "date": day,
                    "label": format_date(self.env, day, date_format="EEE MMM d"),
                    "entries": [
                        {"name": entry.name, "off": entry.day_type == "off", "no_lessons": entry.no_lessons}
                        for entry in entries if entry.date_start <= day <= entry.date_end
                    ],
                } for day in dates]
                rows = []
                for section in sections:
                    lines = section.plan_line_ids.filtered(
                        lambda l: l.date and l.date <= dates[-1] and (l.date_end or l.date) >= dates[0]
                    ).sorted("sequence")
                    cells = []
                    for day in dates:
                        cells.append([
                            {
                                "name": line.name,
                                "topic": line.topic or "",
                                "unit": line.unit or "",
                                "item_note": line.item_note or "",
                                "note": line.note or "",
                                "done": line.done,
                                "files": len(line.item_id.attachment_ids),
                            }
                            for line in lines if line.date <= day <= (line.date_end or line.date)
                        ])
                    rows.append({"section": section, "cells": cells})
                pages.append({"teacher": teacher, "monday": monday, "days": days, "rows": rows})
        return pages

    def action_print(self):
        self.ensure_one()
        if not any(page["rows"] for page in self._get_pages()):
            raise UserError(_(
                "Nothing to print: the teachers chosen have no classes with a "
                "pacing guide this year."
            ))
        # sudo: only system admins can read report actions.
        return self.env.ref("horizonforge_school_planner.action_report_weekly_plan").sudo().report_action(
            self, config=False
        )
