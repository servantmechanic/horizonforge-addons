from datetime import date, timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools import format_date


class SchoolYear(models.Model):
    _name = "school.year"
    _description = "School Year"
    _order = "date_start desc"

    name = fields.Char(
        required=True,
        help="For example 2026-27.",
    )
    date_start = fields.Date(
        string="Start Date",
        required=True,
    )
    date_end = fields.Date(
        string="End Date",
        required=True,
    )
    is_current = fields.Boolean(
        string="Current Year",
        copy=False,
        help="The year the school is working in. Only one year is current at "
        "a time: marking a year current unmarks the others.",
    )
    active = fields.Boolean(default=True)
    period_ids = fields.One2many(
        "school.period",
        "year_id",
        string="Grading Periods",
    )
    section_ids = fields.One2many(
        "school.section",
        "year_id",
        string="Classes",
    )
    section_count = fields.Integer(compute="_compute_section_count")
    day_off_ids = fields.One2many(
        "school.calendar.day",
        "year_id",
        string="Calendar",
        help="Days off (holidays and breaks) and days shown for information. "
        "Weekends are always off.",
    )

    _name_unique = models.Constraint(
        "UNIQUE(name)",
        "School year names must be unique.",
    )
    _dates_ordered = models.Constraint(
        "CHECK(date_end > date_start)",
        "The school year must end after it starts.",
    )

    def _compute_section_count(self):
        counts = dict(self.env["school.section"]._read_group(
            [("year_id", "in", self.ids)],
            ["year_id"],
            ["__count"],
        ))
        for year in self:
            year.section_count = counts.get(year, 0)

    @api.model
    def _get_current(self):
        """Return the current school year (empty if none is marked)."""
        return self.search([("is_current", "=", True)], limit=1)

    @api.model_create_multi
    def create(self, vals_list):
        years = super().create(vals_list)
        years._keep_one_current()
        years._add_holidays()
        return years

    @api.model
    def _easter(self, year):
        """Easter Sunday (Gregorian calendar)."""
        a, b, c = year % 19, year // 100, year % 100
        d, e = b // 4, b % 4
        g = (b - (b + 8) // 25 + 1) // 3
        h = (19 * a + b - d - g + 15) % 30
        i, k = c // 4, c % 4
        l = (32 + 2 * e + 2 * i - h - k) % 7
        m = (a + 11 * h + 22 * l) // 451
        month, day = divmod(h + l - 7 * m + 114, 31)
        return date(year, month, day + 1)

    @api.model
    def _holidays(self, year):
        """The holidays shown on the school calendar, for a calendar year."""
        easter = self._easter(year)
        november = date(year, 11, 1)
        thanksgiving = november + timedelta(days=(3 - november.weekday()) % 7 + 21)
        return [
            (_("Good Friday"), easter - timedelta(days=2)),
            (_("Easter"), easter),
            (_("Thanksgiving"), thanksgiving),
            (_("Christmas"), date(year, 12, 25)),
        ]

    def _add_holidays(self):
        """Put the holidays that fall in the year on its calendar, for
        information: school stays in session unless a day off says
        otherwise. A holiday already there (same name or a one-day entry on
        that date) is left alone."""
        vals_list = []
        for year in self:
            names = set(year.day_off_ids.mapped("name"))
            dates = {d.date_start for d in year.day_off_ids if d.date_start == d.date_end}
            for calendar_year in range(year.date_start.year, year.date_end.year + 1):
                for name, day in self._holidays(calendar_year):
                    if year.date_start <= day <= year.date_end and name not in names and day not in dates:
                        vals_list.append({
                            "year_id": year.id, "name": name, "date_start": day, "day_type": "info",
                        })
        return self.env["school.calendar.day"].create(vals_list)

    def action_add_holidays(self):
        added = self._add_holidays()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if added else "info",
                "message": _("%(count)s holidays added to the calendar.", count=len(added)),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def write(self, vals):
        res = super().write(vals)
        if vals.get("is_current"):
            self._keep_one_current()
        return res

    def _keep_one_current(self):
        current = self.filtered("is_current")
        if not current:
            return
        keep = current[-1]
        others = self.search([("is_current", "=", True), ("id", "!=", keep.id)])
        if others:
            # super(): no need to run this check again for the unmarked years
            super(SchoolYear, others).write({"is_current": False})

    @api.constrains("date_start", "date_end")
    def _check_periods_inside(self):
        for year in self:
            outside = year.period_ids.filtered(
                lambda p: p.date_start < year.date_start or p.date_end > year.date_end
            )
            if outside:
                raise ValidationError(_(
                    "Grading period %(period)s falls outside school year %(year)s.",
                    period=outside[0].name,
                    year=year.name,
                ))

    def _get_school_days(self, date_from=None, date_to=None):
        """Return the school days of the year between two dates (both
        included): Monday to Friday, minus the days off."""
        self.ensure_one()
        day = max(date_from or self.date_start, self.date_start)
        last = min(date_to or self.date_end, self.date_end)
        off = self.day_off_ids.filtered(lambda d: d.day_type == "off")
        days = []
        while day <= last:
            if day.weekday() < 5 and not any(
                d.date_start <= day <= d.date_end for d in off
            ):
                days.append(day)
            day += timedelta(days=1)
        return days

    def _get_calendar_months(self):
        """The months of the year for the printed calendar. Each month has
        its weeks (Sunday to Saturday) of day cells, with the CSS class that
        shades them, and its number of school days."""
        self.ensure_one()
        # A day off wins over a day shown only when both fall on a date.
        marks = {}
        for entry in self.day_off_ids.sorted(lambda d: d.day_type == "off"):
            day = entry.date_start
            while day <= entry.date_end:
                marks[day] = entry
                day += timedelta(days=1)
        school_days = self._get_school_days()
        period_ends = set(self.period_ids.mapped("date_end"))
        months = []
        month = self.date_start.replace(day=1)
        while month <= self.date_end:
            next_month = month + relativedelta(months=1)
            day = month - timedelta(days=(month.weekday() + 1) % 7)
            weeks = []
            while day < next_month:
                week = []
                for _weekday in range(7):
                    week.append(self._calendar_cell(day, month, marks, period_ends))
                    day += timedelta(days=1)
                weeks.append(week)
            months.append({
                "name": format_date(self.env, month, date_format="MMMM yyyy"),
                "weeks": weeks,
                "school_days": len([d for d in school_days if month <= d < next_month]),
            })
            month = next_month
        return months

    def _calendar_cell(self, day, month, marks, period_ends):
        if day.month != month.month:
            return {"day": "", "class": ""}
        entry = marks.get(day)
        if day < self.date_start or day > self.date_end:
            css = "o_out"
        elif entry and entry.day_type == "off":
            css = "o_off"
        elif entry:
            css = "o_info"
        elif day.weekday() >= 5:
            css = "o_weekend"
        else:
            css = ""
        if day in period_ends or day in (self.date_start, self.date_end):
            css += " o_mark"
        return {"day": day.day, "class": css.strip()}

    def _get_calendar_entries(self):
        """The days off and days shown only, for the list under the months."""
        self.ensure_one()
        rows = []
        for entry in self.day_off_ids.sorted(lambda d: (d.date_start, d.date_end)):
            dates = format_date(self.env, entry.date_start, date_format="EEE MMM d")
            if entry.date_end != entry.date_start:
                dates += " – " + format_date(self.env, entry.date_end, date_format="EEE MMM d")
            rows.append({"dates": dates, "name": entry.name, "off": entry.day_type == "off"})
        return rows

    def action_print_calendar(self):
        # sudo: only system admins can read report actions. config=False:
        # under sudo, Odoo would ask every user to set up the report layout.
        return self.env.ref(
            "horizonforge_school_core.action_report_school_calendar"
        ).sudo().report_action(self, config=False)

    @api.model
    def action_print_calendar_for_date(self, day):
        """Print the calendar of the school year around a date (the one shown
        on the calendar screen), else of the current year."""
        day = fields.Date.to_date(day)
        year = self.search(
            [("date_start", "<=", day), ("date_end", ">=", day)], limit=1
        ) or self._get_current()
        if not year:
            raise UserError(_("Add a school year first."))
        return year.action_print_calendar()

    def _generate_periods(self, count, name):
        """Split the year into ``count`` grading periods of about the same
        length, each ending on a Friday (the last one on the year's last
        day). Return their values for ``period_ids``."""
        self.ensure_one()
        return self._period_vals(self.date_start, self.date_end, count, name)

    @api.model
    def _period_vals(self, date_start, date_end, count, name):
        total = (date_end - date_start).days + 1
        vals_list = []
        start = date_start
        for number in range(1, count + 1):
            if number == count:
                end = date_end
            else:
                end = date_start + timedelta(days=round(total * number / count) - 1)
                # The nearest Friday.
                ahead = (4 - end.weekday()) % 7
                end += timedelta(days=ahead if ahead <= 3 else ahead - 7)
            if end < start or end > date_end:
                break
            vals_list.append(Command.create({
                "name": f"{name} {number}",
                "sequence": number,
                "date_start": start,
                "date_end": end,
            }))
            start = end + timedelta(days=3)  # the Monday after
            if start > date_end:
                break
        return vals_list

    def _generate_sections(self):
        """Create the year's missing classes from the homerooms: one per
        course of each homeroom's grade levels. Return the new classes."""
        self.ensure_one()
        Section = self.env["school.section"]
        existing = {
            (section.course_id, section.homeroom_id)
            for section in Section.with_context(active_test=False).search(
                [("year_id", "=", self.id)]
            )
        }
        vals_list = []
        for homeroom in self.env["school.homeroom"].search([]):
            courses = self.env["school.course"].search(
                [("grade_level_ids", "in", homeroom.grade_level_ids.ids)]
            )
            for course in courses:
                if (course, homeroom) in existing:
                    continue
                vals_list.append({
                    "course_id": course.id,
                    "year_id": self.id,
                    "homeroom_id": homeroom.id,
                    "teacher_id": (course.teacher_id or homeroom.teacher_id).id,
                })
        return Section.create(vals_list)

    def action_generate_sections(self):
        self.ensure_one()
        sections = self._generate_sections()
        self.section_ids.action_enroll_grade_levels()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success" if sections else "info",
                "message": _(
                    "%(count)s classes created. Students are enrolled in "
                    "the classes of their homeroom and grade level.",
                    count=len(sections),
                ),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    def action_open_calendar(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_core.school_calendar_day_action"
        )
        action["domain"] = [("year_id", "=", self.id)]
        action["context"] = {"default_year_id": self.id}
        return action

    def action_set_current(self):
        self.ensure_one()
        self.is_current = True

    def action_open_sections(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_core.school_section_action"
        )
        action["domain"] = [("year_id", "=", self.id)]
        action["context"] = {"default_year_id": self.id}
        return action
