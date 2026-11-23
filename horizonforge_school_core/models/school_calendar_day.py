from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolCalendarDay(models.Model):
    _name = "school.calendar.day"
    _description = "Calendar Entry"
    _order = "date_start"

    year_id = fields.Many2one(
        "school.year",
        string="School Year",
        required=True,
        ondelete="cascade",
        index=True,
        default=lambda self: self.env["school.year"]._get_current(),
    )
    name = fields.Char(
        required=True,
        help="For example Thanksgiving break or Zoo field trip.",
    )
    date_start = fields.Date(
        string="First Day",
        required=True,
    )
    date_end = fields.Date(
        string="Last Day",
        compute="_compute_date_end",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="Same as the first day for a single day.",
    )

    day_type = fields.Selection(
        [
            ("off", "No school"),
            ("info", "Shown only"),
        ],
        string="Type",
        default="off",
        required=True,
        help="No school: a day off for everyone, without assignments or "
        "attendance. Shown only: on the calendar for information (a field "
        "trip, a half day), school is in session.",
    )
    is_snow_day = fields.Boolean(
        string="Snow Day",
        help="An unplanned closing (weather, power cut). It uses up one of "
        "the year's planned snow days; once they run out, the last day of "
        "school moves later.",
    )
    audience = fields.Selection(
        [
            ("all", "Everyone"),
            ("grade_level", "Grade levels"),
            ("homeroom", "Homerooms"),
            ("teacher", "Teachers"),
        ],
        string="For",
        default="all",
        required=True,
        help="Who the entry is for. Teachers see the entries for everyone "
        "and those for them (their grade levels, homeroom or themselves).",
    )
    grade_level_ids = fields.Many2many(
        "school.grade.level",
        string="Grade Levels",
    )
    homeroom_ids = fields.Many2many(
        "school.homeroom",
        string="Homerooms",
    )
    teacher_ids = fields.Many2many(
        "res.users",
        string="Teachers",
        domain=lambda self: self.env["school.section"]._teacher_domain(),
    )
    audience_label = fields.Char(
        string="Who",
        compute="_compute_audience_label",
    )
    is_for_me = fields.Boolean(
        string="For Me",
        compute="_compute_is_for_me",
        search="_search_is_for_me",
        help="The entry is for everyone, or for the user's grade levels, "
        "homeroom or the user.",
    )
    color = fields.Integer(compute="_compute_color")

    _dates_ordered = models.Constraint(
        "CHECK(date_end >= date_start)",
        "A calendar entry can't end before it starts.",
    )

    @api.depends("day_type", "audience")
    def _compute_color(self):
        for day in self:
            if day.day_type == "off":
                day.color = 1
            else:
                day.color = 10 if day.audience == "all" else 4

    @api.depends("date_start")
    def _compute_date_end(self):
        for day in self:
            if not day.date_end or (day.date_start and day.date_end < day.date_start):
                day.date_end = day.date_start

    @api.depends("audience", "grade_level_ids", "homeroom_ids", "teacher_ids")
    def _compute_audience_label(self):
        for day in self:
            if day.audience == "grade_level":
                day.audience_label = ", ".join(day.grade_level_ids.mapped("name"))
            elif day.audience == "homeroom":
                day.audience_label = ", ".join(day.homeroom_ids.mapped("name"))
            elif day.audience == "teacher":
                day.audience_label = ", ".join(day.teacher_ids.mapped("name"))
            else:
                day.audience_label = False

    @api.model
    def _for_me_domain(self, user=None):
        """Entries for everyone, and those for ``user``'s grade levels,
        homeroom or themselves (default: the current user)."""
        user = user or self.env.user
        # sudo: teachers can't read other teachers' classes, but their own
        # grade levels come from them.
        sections = self.env["school.section"].sudo().search([
            ("year_id.is_current", "=", True),
            "|", ("teacher_id", "=", user.id), ("co_teacher_ids", "in", user.id),
        ])
        homerooms = self.env["school.homeroom"].sudo().search([("teacher_id", "=", user.id)])
        levels = sections.course_id.grade_level_ids | homerooms.grade_level_ids
        return [
            "|", "|", "|",
            ("audience", "=", "all"),
            "&", ("audience", "=", "teacher"), ("teacher_ids", "in", user.id),
            "&", ("audience", "=", "homeroom"), ("homeroom_ids", "in", homerooms.ids),
            "&", ("audience", "=", "grade_level"), ("grade_level_ids", "in", levels.ids),
        ]

    def _compute_is_for_me(self):
        mine = self.search([("id", "in", self.ids)] + self._for_me_domain())
        for day in self:
            day.is_for_me = day in mine

    def _search_is_for_me(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            return NotImplemented
        wanted = bool(value) if operator in ("=", "!=") else True in value
        if operator in ("!=", "not in"):
            wanted = not wanted
        domain = self._for_me_domain()
        return domain if wanted else ["!"] + domain

    @api.onchange("day_type")
    def _onchange_day_type(self):
        if self.day_type == "off":
            self.audience = "all"
        else:
            self.is_snow_day = False

    @api.constrains("date_start", "date_end", "year_id")
    def _check_inside_year(self):
        for day in self:
            year = day.year_id
            if day.date_end < year.date_start or day.date_start > year.date_end:
                raise ValidationError(_(
                    "%(name)s is outside school year %(year)s (%(start)s to %(end)s).",
                    name=day.name,
                    year=year.name,
                    start=year.date_start,
                    end=year.date_end,
                ))

    @api.constrains("day_type", "audience", "is_snow_day")
    def _check_audience(self):
        for day in self:
            if day.day_type == "off" and day.audience != "all":
                raise ValidationError(_(
                    "%(name)s: a day without school is for everyone. For a "
                    "field trip or a day some students miss, choose Shown only.",
                    name=day.name,
                ))
            if day.is_snow_day and day.day_type != "off":
                raise ValidationError(_(
                    "%(name)s: a snow day is a day without school.",
                    name=day.name,
                ))

    # A change to the days off can move the last day of school.

    @api.model_create_multi
    def create(self, vals_list):
        days = super().create(vals_list)
        days.year_id._apply_school_days_target()
        return days

    def write(self, vals):
        years = self.year_id
        res = super().write(vals)
        if {"date_start", "date_end", "day_type", "is_snow_day", "year_id"} & set(vals):
            (years | self.year_id)._apply_school_days_target()
        return res

    def unlink(self):
        years = self.year_id
        res = super().unlink()
        years.exists()._apply_school_days_target()
        return res
