from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.safe_eval import safe_eval


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
        "by the principal.",
    )

    is_current = fields.Boolean(
        string="Current Grading Period",
        compute="_compute_is_current",
        search="_search_is_current",
        help="Today falls in this grading period.",
    )
    is_previous = fields.Boolean(
        string="Previous Grading Period",
        compute="_compute_is_current",
        search="_search_is_previous",
        help="The last grading period that ended before today.",
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
    def _get_current(self):
        today = fields.Date.context_today(self)
        return self.search([("date_start", "<=", today), ("date_end", ">=", today)], limit=1)

    @api.model
    def _get_previous(self):
        today = fields.Date.context_today(self)
        return self.search([("date_end", "<", today)], order="date_end desc", limit=1)

    def _compute_is_current(self):
        current, previous = self._get_current(), self._get_previous()
        for period in self:
            period.is_current = period == current
            period.is_previous = period == previous

    def _search_is_current(self, operator, value):
        return self._search_flag(self._get_current(), operator, value)

    def _search_is_previous(self, operator, value):
        return self._search_flag(self._get_previous(), operator, value)

    def _search_flag(self, periods, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            return NotImplemented
        wanted = bool(value) if operator in ("=", "!=") else True in value
        if operator in ("!=", "not in"):
            wanted = not wanted
        return [("id", "in" if wanted else "not in", periods.ids)]

    @api.model
    def _get_for_date(self, date):
        """Return the grading period that contains ``date`` (empty if none)."""
        return self.search(
            [("date_start", "<=", date), ("date_end", ">=", date)],
            limit=1,
        )

    @api.model
    def _school_list_action(self, xmlid, mine_filter=None):
        """The window action ``xmlid`` opened on the current grading period
        (the last one that ended, between periods), picked in its side panel,
        with ``mine_filter`` on for teachers outside the office."""
        action = self.env["ir.actions.act_window"]._for_xml_id(xmlid)
        context = safe_eval(action.get("context") or "{}", {"uid": self.env.uid})
        period = self._get_current() or self._get_previous()
        if period:
            context["searchpanel_default_period_id"] = period.id
        if mine_filter and not self.env.user.has_group("horizonforge_school_core.group_school_office"):
            context["search_default_" + mine_filter] = 1
        action["context"] = context
        return action

