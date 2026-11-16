from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ENTRY_MODES = [
    ("percent", "Percent"),
    ("points", "Points"),
    ("wrong", "Number wrong"),
]


class SchoolAssignment(models.Model):
    _name = "school.assignment"
    _description = "Assignment"
    _order = "date, sequence, id"

    section_id = fields.Many2one(
        "school.section",
        string="Class",
        required=True,
        ondelete="cascade",
        index=True,
    )
    name = fields.Char(required=True)
    date = fields.Date(
        required=True,
        default=fields.Date.context_today,
    )
    period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        compute="_compute_period_id",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        ondelete="restrict",
        index=True,
        domain="[('year_id', '=', year_id)]",
        help="Set from the date.",
    )
    year_id = fields.Many2one(related="section_id.year_id")
    category_id = fields.Many2one(
        "school.score.category",
        string="Category",
        required=True,
        ondelete="restrict",
        default=lambda self: self.env["school.score.category"].search([], limit=1),
    )
    max_points = fields.Float(
        default=100.0,
        required=True,
    )
    entry_mode = fields.Selection(
        ENTRY_MODES,
        compute="_compute_entry_mode",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="What the teacher types: a percent, the points earned, or the "
        "number of wrong answers.",
    )
    sequence = fields.Integer(default=10)
    template_id = fields.Many2one(
        "school.assignment.template",
        string="Schedule",
        ondelete="set null",
        index=True,
        copy=False,
    )
    score_ids = fields.One2many(
        "school.score",
        "assignment_id",
        string="Scores",
    )

    _max_points_positive = models.Constraint(
        "CHECK(max_points > 0)",
        "Max points must be more than 0.",
    )

    @api.depends("date", "section_id")
    def _compute_period_id(self):
        for assignment in self:
            year = assignment.section_id.year_id
            date = assignment.date
            if not year or not date:
                assignment.period_id = assignment.period_id
                continue
            if (
                assignment.period_id.year_id == year
                and assignment.period_id.date_start <= date <= assignment.period_id.date_end
            ):
                continue
            assignment.period_id = year.period_ids.filtered(
                lambda p: p.date_start <= date <= p.date_end
            )[:1]

    @api.depends("section_id")
    def _compute_entry_mode(self):
        for assignment in self:
            if not assignment.entry_mode:
                assignment.entry_mode = assignment.section_id._get_entry_mode()

    @api.constrains("period_id", "section_id")
    def _check_period(self):
        for assignment in self:
            if assignment.period_id.year_id != assignment.section_id.year_id:
                raise ValidationError(_(
                    "The grading period of %(name)s isn't in the class's school year.",
                    name=assignment.name,
                ))

    @api.constrains("max_points", "entry_mode")
    def _check_scores_fit(self):
        self.score_ids._check_value()

    def _check_unlocked(self):
        """Locked grading periods only change for school administrators."""
        if self.env.su or self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            return
        locked = self.period_id.filtered("locked")
        if locked:
            raise UserError(_(
                "%(period)s is locked. Ask a school administrator to change its grades.",
                period=locked[0].display_name,
            ))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("period_id") and vals.get("section_id") and vals.get("date"):
                # A clear message instead of the database's not-null error.
                section = self.env["school.section"].browse(vals["section_id"])
                date = fields.Date.to_date(vals["date"])
                if not section.year_id.period_ids.filtered(
                    lambda p: p.date_start <= date <= p.date_end
                ):
                    raise UserError(_(
                        "%(date)s isn't in any grading period of %(year)s.",
                        date=fields.Date.to_string(date),
                        year=section.year_id.name,
                    ))
        assignments = super().create(vals_list)
        assignments._check_unlocked()
        return assignments

    def write(self, vals):
        self._check_unlocked()
        res = super().write(vals)
        if "date" in vals or "period_id" in vals:
            if any(not assignment.period_id for assignment in self):
                raise UserError(_("That date isn't in any grading period of the school year."))
            self._check_unlocked()
        return res

    def unlink(self):
        self._check_unlocked()
        return super().unlink()
