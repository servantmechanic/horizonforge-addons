from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolPeriod(models.Model):
    _name = "school.period"
    _description = "Grading Period"
    _order = "year_id desc, sequence, date_start"

    year_id = fields.Many2one(
        "school.year",
        string="School Year",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(
        required=True,
        help="For example Quarter 1.",
    )
    sequence = fields.Integer(default=10)
    date_start = fields.Date(
        string="Start Date",
        required=True,
    )
    date_end = fields.Date(
        string="End Date",
        required=True,
    )
    locked = fields.Boolean(
        copy=False,
        help="Locked periods are closed: their grades can only be changed "
        "by a school administrator.",
    )

    _dates_ordered = models.Constraint(
        "CHECK(date_end >= date_start)",
        "A grading period can't end before it starts.",
    )

    @api.depends("name", "year_id.name")
    @api.depends_context("school_period_short_name")
    def _compute_display_name(self):
        short = self.env.context.get("school_period_short_name")
        for period in self:
            if short or not period.year_id:
                period.display_name = period.name
            else:
                period.display_name = f"{period.year_id.name} {period.name}"

    @api.constrains("date_start", "date_end", "year_id")
    def _check_dates(self):
        for period in self:
            year = period.year_id
            if period.date_start < year.date_start or period.date_end > year.date_end:
                raise ValidationError(_(
                    "Grading period %(period)s must fall inside school year "
                    "%(year)s (%(start)s to %(end)s).",
                    period=period.name,
                    year=year.name,
                    start=year.date_start,
                    end=year.date_end,
                ))
            overlap = self.search([
                ("year_id", "=", year.id),
                ("id", "!=", period.id),
                ("date_start", "<=", period.date_end),
                ("date_end", ">=", period.date_start),
            ], limit=1)
            if overlap:
                raise ValidationError(_(
                    "Grading periods %(period)s and %(other)s overlap.",
                    period=period.name,
                    other=overlap.name,
                ))

    @api.model
    def _get_for_date(self, date):
        """Return the grading period that contains ``date`` (empty if none)."""
        return self.search(
            [("date_start", "<=", date), ("date_end", ">=", date)],
            limit=1,
        )
