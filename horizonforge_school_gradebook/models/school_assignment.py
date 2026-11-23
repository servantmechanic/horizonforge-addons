import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

ENTRY_MODES = [
    ("percent", "Percent"),
    ("points", "Points"),
    ("wrong", "Number wrong"),
    ("letter", "Letter"),
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
    course_id = fields.Many2one(
        related="section_id.course_id",
        store=True,
        index=True,
    )
    homeroom_id = fields.Many2one(
        related="section_id.homeroom_id",
        store=True,
    )
    grade_level_ids = fields.Many2many(
        related="section_id.course_id.grade_level_ids",
        string="Grade Levels",
        store=True,
    )
    unscored_count = fields.Integer(
        string="To Score",
        compute="_compute_unscored_count",
        help="Students enrolled in the class on the assignment's date who "
             "have no score yet. Missing and Excused count as scored.",
    )
    is_unscored = fields.Boolean(
        string="Not Fully Scored",
        compute="_compute_unscored_count",
        search="_search_is_unscored",
        help="Dated today or earlier, with students still to score.",
    )
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
        aggregator=None,  # A total of max points means nothing.
    )
    entry_mode = fields.Selection(
        ENTRY_MODES,
        compute="_compute_entry_mode",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="What the teacher types: a percent, the points earned, the "
        "number of wrong answers, or a letter (A-), which counts as the "
        "grading scale's value for that letter.",
    )
    sequence = fields.Integer(default=10)
    template_id = fields.Many2one(
        "school.assignment.template",
        string="Schedule",
        ondelete="set null",
        index=True,
        copy=False,
        domain="[('course_id', '=', course_id)]",
        help="Pick one to fill in the name, category, points and entry mode, "
        "for example a test that is placed by hand.",
    )
    score_ids = fields.One2many(
        "school.score",
        "assignment_id",
        string="Scores",
    )
    note = fields.Text(
        string="Notes",
        help="For the teacher: what the assignment covers, pages, answers.",
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "school_assignment_attachment_rel",
        "assignment_id",
        "attachment_id",
        string="Files",
        help="The worksheet, quiz or answer key to print. Whoever can see the "
        "assignment can open them.",
    )
    attachment_count = fields.Integer(
        string="Number of Files",
        compute="_compute_attachment_count",
    )

    _max_points_positive = models.Constraint(
        "CHECK(max_points > 0)",
        "Max points must be more than 0.",
    )

    @api.onchange("template_id", "date")
    def _onchange_template_id(self):
        template = self.template_id
        if not template or not self.section_id or not self.date:
            return
        if self._origin.template_id != template:
            self.category_id = template.category_id
            self.max_points = template.max_points
            self.entry_mode = template.entry_mode or self.section_id._get_entry_mode()
        if not self._origin.id:
            self.name = template._next_name(self.section_id, self.date)

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        for assignment in self:
            assignment.attachment_count = len(assignment.attachment_ids)

    def _link_files(self):
        """Tie the uploaded files to the assignment, so that who may open
        them follows who may see it."""
        for assignment in self:
            loose = assignment.attachment_ids.sudo().filtered(
                lambda a: a.res_model != self._name or a.res_id != assignment.id
            )
            loose.write({"res_model": self._name, "res_id": assignment.id})

    @api.model
    def _suggest_name(self, section, category, exclude=None):
        """The name of the next assignment of a category in a class, going
        on from the last one: Lesson 12 after Lesson 11. Without one yet,
        the course's schedule name for the category (Lesson 1), else the
        category's name."""
        domain = [("section_id", "=", section.id), ("category_id", "=", category.id)]
        if exclude:
            domain.append(("id", "not in", exclude.ids))
        last = self.search(domain, order="date desc, sequence desc, id desc", limit=1)
        match = re.match(r"^(.*\S)\s+(\d+)$", last.name or "")
        if match:
            return f"{match.group(1)} {int(match.group(2)) + 1}"
        if last:
            base = last.name
        else:
            template = section.course_id.assignment_template_ids.filtered(
                lambda t: t.category_id == category
            )[:1]
            # Lesson/Homework: Lesson 1.
            base = template.name or category.name.split("/")[0].strip() or category.name
        # Numbered among the ones of that name: Quiz 2 after Quiz.
        same = self.search_count(domain + ["|", ("name", "=", base), ("name", "=like", f"{base} %")])
        return f"{base} {same + 1}"

    def _unscored_counts(self, ids=None):
        """{assignment id: students without a score}, for the assignments
        ``ids`` (all, if None) dated today or earlier."""
        query = """
            SELECT a.id, COUNT(*)
              FROM school_assignment a
              JOIN school_enrollment e
                ON e.section_id = a.section_id
               AND e.date_start <= a.date
               AND (e.date_end IS NULL OR e.date_end >= a.date)
              JOIN school_student st ON st.id = e.student_id AND st.active
         LEFT JOIN school_score s ON s.assignment_id = a.id AND s.student_id = e.student_id
             WHERE s.id IS NULL AND a.date <= %s
        """
        params = [fields.Date.context_today(self)]
        if ids is not None:
            query += " AND a.id = ANY(%s)"
            params.append(list(ids))
        self.env.flush_all()
        self.env.cr.execute(query + " GROUP BY a.id", params)
        return dict(self.env.cr.fetchall())

    def _compute_unscored_count(self):
        counts = self._unscored_counts(self.ids) if self.ids else {}
        for assignment in self:
            assignment.unscored_count = counts.get(assignment.id, 0)
            assignment.is_unscored = bool(assignment.unscored_count)

    def _search_is_unscored(self, operator, value):
        if operator not in ("=", "!=", "in", "not in"):
            return NotImplemented
        wanted = bool(value) if operator in ("=", "!=") else True in value
        if operator in ("!=", "not in"):
            wanted = not wanted
        ids = list(self._unscored_counts())
        return [("id", "in" if wanted else "not in", ids)]

    @api.model
    def action_open_list(self):
        return self.env["school.period"]._school_list_action(
            "horizonforge_school_gradebook.school_assignment_action", "my_classes")

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
        """Locked grading periods only change for the principal."""
        if self.env.su or self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            return
        locked = self.period_id.filtered("locked")
        if locked:
            raise UserError(_(
                "%(period)s is locked. Ask the principal to change its grades.",
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
        assignments.filtered("attachment_ids")._link_files()
        return assignments

    def write(self, vals):
        self._check_unlocked()
        res = super().write(vals)
        if "date" in vals or "period_id" in vals:
            if any(not assignment.period_id for assignment in self):
                raise UserError(_("That date isn't in any grading period of the school year."))
            self._check_unlocked()
        if "attachment_ids" in vals:
            self._link_files()
        return res

    def unlink(self):
        self._check_unlocked()
        return super().unlink()
