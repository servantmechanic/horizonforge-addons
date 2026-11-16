from datetime import timedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class SchoolYearSetup(models.TransientModel):
    _name = "school.year.setup"
    _description = "New Year Setup"

    source_year_id = fields.Many2one(
        "school.year",
        string="Based On",
        default=lambda self: self._default_source_year(),
        help="The year to copy grading periods, days off and classes from. "
        "Leave empty for the school's first year.",
    )
    name = fields.Char(
        compute="_compute_from_source",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
    )
    date_start = fields.Date(
        string="Start Date",
        compute="_compute_from_source",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
    )
    date_end = fields.Date(
        string="End Date",
        compute="_compute_from_source",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
    )
    period_mode = fields.Selection(
        [
            ("copy", "Copy last year's periods"),
            ("generate", "Generate equal periods"),
            ("none", "Don't create periods"),
        ],
        string="Grading Periods",
        compute="_compute_period_mode",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="Copying moves last year's periods to the new dates. Generating "
        "splits the year into equal periods that each end on a Friday.",
    )
    period_count = fields.Integer(
        string="Number of Periods",
        default=6,
    )
    period_name = fields.Char(
        string="Period Name",
        default="Period",
        help="The periods are named with a number: Period 1, Period 2 and so on.",
    )
    copy_days_off = fields.Boolean(
        string="Copy Days Off",
        default=True,
        help="Copy last year's holidays and breaks, 52 weeks later. Check "
        "the dates afterwards in the school calendar.",
    )
    class_mode = fields.Selection(
        [
            ("copy", "Copy last year's classes"),
            ("homeroom", "Generate from homerooms"),
            ("none", "Don't create classes"),
        ],
        string="Classes",
        compute="_compute_period_mode",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="Copying keeps last year's courses, teachers and homerooms. "
        "Generating builds one class per course of each homeroom's grade levels.",
    )
    promote_students = fields.Boolean(
        default=True,
        help="Move every active student up one grade level.",
    )
    archive_graduates = fields.Boolean(
        default=True,
        help="Archive the students of the top grade level instead of "
        "leaving them there.",
    )
    graduate_ids = fields.Many2many(
        "school.student",
        string="Graduating Students",
        compute="_compute_graduate_ids",
    )
    enroll_students = fields.Boolean(
        default=True,
        help="Enroll each student in the new classes of their homeroom and grade level.",
    )
    make_current = fields.Boolean(
        string="Make It the Current Year",
        default=True,
    )

    @api.model
    def _default_source_year(self):
        Year = self.env["school.year"]
        return Year._get_current() or Year.search([], limit=1)

    @api.depends("source_year_id")
    def _compute_from_source(self):
        for wizard in self:
            source = wizard.source_year_id
            if not source:
                # First year: August to May around the coming school year.
                today = fields.Date.context_today(wizard)
                first = today.year if today.month <= 7 else today.year + 1
                if not wizard.date_start:
                    wizard.date_start = today.replace(year=first, month=8, day=15)
                    wizard.date_end = today.replace(year=first + 1, month=5, day=31)
                    wizard.name = f"{first}-{(first + 1) % 100:02d}"
                continue
            # 52 weeks later: the same weekdays as last year.
            wizard.date_start = source.date_start + timedelta(weeks=52)
            wizard.date_end = source.date_end + timedelta(weeks=52)
            wizard.name = f"{wizard.date_start.year}-{wizard.date_end.year % 100:02d}"

    @api.depends("source_year_id")
    def _compute_period_mode(self):
        for wizard in self:
            source = wizard.source_year_id
            wizard.period_mode = "copy" if source.period_ids else "generate"
            wizard.class_mode = "copy" if source.section_ids else "homeroom"

    @api.depends("promote_students")
    def _compute_graduate_ids(self):
        top = self.env["school.grade.level"].search([], order="sequence desc, id desc", limit=1)
        graduates = self.env["school.student"].search([("grade_level_id", "=", top.id)]) if top else False
        for wizard in self:
            wizard.graduate_ids = graduates if wizard.promote_students else False

    def _promote_students(self):
        levels = self.env["school.grade.level"].search([])
        if not levels:
            return
        Student = self.env["school.student"]
        if self.archive_graduates:
            Student.search([("grade_level_id", "=", levels[-1].id)]).action_archive()
        # Top grade first, so nobody is moved twice.
        for index in range(len(levels) - 2, -1, -1):
            Student.search([("grade_level_id", "=", levels[index].id)]).write(
                {"grade_level_id": levels[index + 1].id}
            )

    def _period_vals(self):
        source = self.source_year_id
        shift = self.date_start - source.date_start
        vals_list = []
        for period in source.period_ids:
            start = max(period.date_start + shift, self.date_start)
            end = min(period.date_end + shift, self.date_end)
            if start <= end:
                vals_list.append(Command.create({
                    "name": period.name,
                    "sequence": period.sequence,
                    "date_start": start,
                    "date_end": end,
                }))
        return vals_list

    def _day_off_vals(self):
        shift = self.date_start - self.source_year_id.date_start
        vals_list = []
        # Only the days off: the holidays are worked out again for the new year.
        for day in self.source_year_id.day_off_ids.filtered(lambda d: d.day_type == "off"):
            start = max(day.date_start + shift, self.date_start)
            end = min(day.date_end + shift, self.date_end)
            if start <= end:
                vals_list.append(Command.create({
                    "name": day.name, "date_start": start, "date_end": end,
                }))
        return vals_list

    def _copy_section_vals(self, section, year):
        """Values of ``section`` copied to ``year``. Other addons extend it."""
        return {
            "course_id": section.course_id.id,
            "year_id": year.id,
            "name": section.name,
            "teacher_id": section.teacher_id.id,
            "co_teacher_ids": [Command.set(section.co_teacher_ids.ids)],
            "homeroom_id": section.homeroom_id.id,
        }

    def action_confirm(self):
        self.ensure_one()
        source = self.source_year_id
        if not source and (self.period_mode == "copy" or self.class_mode == "copy"):
            raise UserError(_("Choose the year to copy from."))
        if self.period_mode == "generate" and not 1 <= self.period_count <= 12:
            raise UserError(_("Choose between 1 and 12 grading periods."))
        Year = self.env["school.year"]
        periods = []
        if self.period_mode == "copy":
            periods = self._period_vals()
        elif self.period_mode == "generate":
            periods = Year._period_vals(
                self.date_start, self.date_end, self.period_count, self.period_name or _("Period")
            )
        year = Year.create({
            "name": self.name,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "period_ids": periods,
            "day_off_ids": self._day_off_vals() if source and self.copy_days_off else [],
        })
        if self.promote_students:
            self._promote_students()
        if self.class_mode == "copy":
            self.env["school.section"].create([
                self._copy_section_vals(section, year)
                for section in source.section_ids
                if section.course_id.active
            ])
        elif self.class_mode == "homeroom":
            year._generate_sections()
        if self.enroll_students:
            year.section_ids.action_enroll_grade_levels()
        if self.make_current:
            year.is_current = True
        return {
            "type": "ir.actions.act_window",
            "res_model": "school.year",
            "res_id": year.id,
            "view_mode": "form",
            "target": "current",
        }
