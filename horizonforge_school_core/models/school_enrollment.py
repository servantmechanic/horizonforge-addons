from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class SchoolEnrollment(models.Model):
    _name = "school.enrollment"
    _description = "Enrollment"
    _order = "section_id, student_id, date_start"

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
    date_start = fields.Date(
        string="Start Date",
        compute="_compute_date_start",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
        help="First day in the class. Defaults to the start of the school year.",
    )
    date_end = fields.Date(
        string="End Date",
        help="Last day in the class. Leave empty when the student stays "
        "until the end of the school year.",
    )
    year_id = fields.Many2one(
        related="section_id.year_id",
        store=True,
    )
    course_id = fields.Many2one(
        related="section_id.course_id",
        store=True,
    )
    teacher_id = fields.Many2one(
        related="section_id.teacher_id",
    )

    _dates_ordered = models.Constraint(
        "CHECK(date_end IS NULL OR date_end >= date_start)",
        "An enrollment can't end before it starts.",
    )

    @api.depends("section_id")
    def _compute_date_start(self):
        for enrollment in self:
            if not enrollment.date_start:
                enrollment.date_start = (
                    enrollment.section_id.year_id.date_start
                    or fields.Date.context_today(enrollment)
                )

    @api.depends("student_id", "section_id")
    def _compute_display_name(self):
        for enrollment in self:
            enrollment.display_name = (
                f"{enrollment.student_id.display_name} - "
                f"{enrollment.section_id.display_name}"
            )

    @api.constrains("section_id", "student_id", "date_start", "date_end")
    def _check_no_overlap(self):
        for enrollment in self:
            domain = [
                ("section_id", "=", enrollment.section_id.id),
                ("student_id", "=", enrollment.student_id.id),
                ("id", "!=", enrollment.id),
                "|", ("date_end", "=", False), ("date_end", ">=", enrollment.date_start),
            ]
            if enrollment.date_end:
                domain.append(("date_start", "<=", enrollment.date_end))
            if self.search_count(domain, limit=1):
                raise ValidationError(_(
                    "%(student)s is already enrolled in %(section)s for these dates.",
                    student=enrollment.student_id.display_name,
                    section=enrollment.section_id.display_name,
                ))

    def _is_active_on(self, date):
        """Whether the student is in the class on ``date``."""
        self.ensure_one()
        return self.date_start <= date and (not self.date_end or self.date_end >= date)
