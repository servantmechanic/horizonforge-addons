from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolCalendarDay(models.Model):
    _name = "school.calendar.day"
    _description = "Day Off"
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
        help="For example Thanksgiving break.",
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
        help="Same as the first day for a single day off.",
    )

    day_type = fields.Selection(
        [
            ("off", "No school"),
            ("info", "Shown only"),
        ],
        string="Type",
        default="off",
        required=True,
        help="No school: a day off, without assignments or attendance. "
        "Shown only: on the calendar for information, school is in session.",
    )
    color = fields.Integer(compute="_compute_color")

    _dates_ordered = models.Constraint(
        "CHECK(date_end >= date_start)",
        "A day off can't end before it starts.",
    )

    @api.depends("day_type")
    def _compute_color(self):
        for day in self:
            day.color = 1 if day.day_type == "off" else 10

    @api.depends("date_start")
    def _compute_date_end(self):
        for day in self:
            if not day.date_end or (day.date_start and day.date_end < day.date_start):
                day.date_end = day.date_start

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
