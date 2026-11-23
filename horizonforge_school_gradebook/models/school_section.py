from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .school_assignment import ENTRY_MODES


class SchoolSection(models.Model):
    _inherit = "school.section"

    entry_mode = fields.Selection(
        ENTRY_MODES,
        help="What the teacher types in the gradebook. Leave empty to use "
        "the course's or the school's entry mode.",
    )
    weight_scheme_id = fields.Many2one(
        "school.weight.scheme",
        string="Weight Scheme",
        ondelete="restrict",
        help="Leave empty to use the course's or the school's weight scheme.",
    )
    grading_type = fields.Selection(related="course_id.grading_type")
    assignment_ids = fields.One2many(
        "school.assignment",
        "section_id",
        string="Assignments",
    )

    # Settings resolve from most specific to least: class, course, school.

    def _get_entry_mode(self):
        self.ensure_one()
        return (
            self.entry_mode
            or self.course_id.entry_mode
            or ("letter" if self.grading_type == "letter" else False)
            or self.env.company.school_entry_mode
        )

    def _get_weight_scheme(self):
        self.ensure_one()
        return (
            self.weight_scheme_id
            or self.course_id.weight_scheme_id
            or self.env.company.school_weight_scheme_id
        )

    def _get_grading_scale(self, student=None):
        self.ensure_one()
        return (
            self.course_id.grading_scale_id
            or (student.grade_level_id.grading_scale_id if student else False)
            or self.env.company.school_grading_scale_id
        )

    # Assignment schedules

    def _generate_assignments(self, period):
        """Create the assignments of the course's schedules for ``period``.
        One that falls on a day off moves to the next school day, unless
        that day already has its own or the schedule says to skip it. Days
        that already have theirs are left alone, so it can run again after
        a schedule or the calendar changes. Schedules without weekdays are
        placed by hand and generate nothing."""
        Assignment = self.env["school.assignment"]
        vals_list = []
        for section in self:
            if section.year_id != period.year_id or section.grading_type == "comment":
                continue
            days = section.year_id._get_school_days(period.date_start, period.date_end)
            # A day that became a day off: its scheduled assignments go,
            # unless they already have scores.
            Assignment.search([
                ("section_id", "=", section.id),
                ("period_id", "=", period.id),
                ("template_id", "!=", False),
                ("date", "not in", days),
                ("score_ids", "=", False),
            ]).unlink()
            # School weeks, numbered from the start of the year: a week
            # without any school day isn't counted.
            week_numbers = {}
            for day in section.year_id._get_school_days():
                week_numbers.setdefault(day - timedelta(days=day.weekday()), len(week_numbers) + 1)
            school_days = set(days)
            weekdays_of_period = []
            day = period.date_start
            while day <= period.date_end:
                if day.weekday() < 5:
                    weekdays_of_period.append(day)
                day += timedelta(days=1)
            for template in section.course_id.assignment_template_ids:
                weekdays = template._weekdays()
                if not weekdays:
                    continue  # placed by hand
                existing = Assignment.search([
                    ("section_id", "=", section.id),
                    ("template_id", "=", template.id),
                ])
                taken = sorted(existing.mapped("date"))
                for planned in weekdays_of_period:
                    if planned.weekday() not in weekdays:
                        continue
                    week = week_numbers.get(planned - timedelta(days=planned.weekday()))
                    if not week or not template._in_week(week):
                        continue  # a week without school isn't counted
                    day = planned
                    if day not in school_days:
                        if not template.move_on_day_off:
                            continue
                        # A day off: the next school day of the period, or
                        # the one before when the period ends first.
                        day = next((d for d in days if d > planned), None) or next(
                            (d for d in reversed(days) if d < planned), None
                        )
                    if not day or day in taken:
                        continue
                    name = template.name
                    if template.numbered:
                        number = len([date for date in taken if date < day]) + 1
                        name = f"{name} {number}"
                    taken.append(day)
                    taken.sort()
                    vals_list.append({
                        "section_id": section.id,
                        "template_id": template.id,
                        "name": name,
                        "date": day,
                        "period_id": period.id,
                        "category_id": template.category_id.id,
                        "max_points": template.max_points,
                        "entry_mode": template.entry_mode or section._get_entry_mode(),
                        "sequence": template.sequence,
                    })
        return Assignment.create(vals_list)

    def action_open_period_marks(self):
        self.ensure_one()
        return self.env["school.period.mark"].action_open_marks(self)

    def action_open_gradebook(self):
        self.ensure_one()
        return {
            "type": "ir.actions.client",
            "tag": "school_gradebook_grid",
            "name": _("Gradebook"),
            "context": {"default_section_id": self.id},
        }

    # Gradebook grid

    def _gradebook_can_edit(self, period):
        self.ensure_one()
        user = self.env.user
        if user.has_group("horizonforge_school_core.group_school_admin"):
            return True
        return not period.locked and self._is_my_class(user)

    @api.model
    def _gradebook_sections(self):
        """Classes the user picks from: their own (with their homeroom's
        classes), or all for the office, in the current school year."""
        user = self.env.user
        domain = [("year_id.is_current", "=", True), ("course_id.grading_type", "!=", "comment")]
        if not user.has_group("horizonforge_school_core.group_school_office"):
            domain += self._my_classes_domain(user)
        own = lambda s: not s._is_my_class(user)  # noqa: E731
        return self.search(domain).sorted(
            lambda s: (own(s), s.course_id.sequence, s.course_id.name or "", s.name or "", s.id)
        )

    @api.model
    def gradebook_open(self, section_id=False, period_id=False):
        """Everything the gradebook grid needs for one class and one
        grading period, in a single call."""
        sections = self._gradebook_sections()
        section = self.browse(section_id).exists() if section_id else sections[:1]
        result = {
            "sections": [{"id": s.id, "name": s.display_name} for s in sections | section],
            "enter_direction": self.env.user.school_enter_direction,
            "name_order": self.env.user.school_name_order,
            "cell_letters": self.env.user.school_cell_letters,
            "section_id": section.id,
        }
        if not section:
            return result
        section.check_access("read")
        periods = section.year_id.period_ids
        today = fields.Date.context_today(self)
        current = periods.filtered(lambda p: p.date_start <= today <= p.date_end)[:1]
        period = periods.filtered(lambda p: p.id == period_id)
        if not period:
            period = (
                current
                or periods.filtered(lambda p: p.date_start > today)[:1]
                or periods[-1:]
            )
        result.update({
            "periods": [{"id": p.id, "name": p.name, "locked": p.locked} for p in periods],
            "period_id": period.id,
            "current_period_id": current.id,
            "today": fields.Date.to_string(today),
            "entry_mode": section._get_entry_mode(),
            "letter_only": section.grading_type == "letter",
            "grade_decimals": self.env.company.school_grade_decimals,
            "can_edit": bool(period) and section._gradebook_can_edit(period),
            "locked": period.locked,
            "has_schedule": bool(section.course_id.assignment_template_ids.filtered("is_scheduled")),
            "categories": [
                {"id": c.id, "name": c.name, "code": c.code, "color": c.color}
                for c in self.env["school.score.category"].with_context(active_test=False).search([])
            ],
            "assignments": [],
            "students": [],
            "scores": [],
        })
        if not period:
            return result
        assignments = self.env["school.assignment"].search([
            ("section_id", "=", section.id), ("period_id", "=", period.id),
        ])
        result["assignments"] = [
            {
                "id": a.id,
                "name": a.name,
                "date": fields.Date.to_string(a.date),
                "category_id": a.category_id.id,
                "max_points": a.max_points,
                "entry_mode": a.entry_mode,
            }
            for a in assignments
        ]
        # Students in the class at any time during the period, including
        # withdrawn ones: their scores still show.
        enrollments = section.enrollment_ids.filtered(
            lambda e: e.date_start <= period.date_end
            and (not e.date_end or e.date_end >= period.date_start)
        )
        students = section._gradebook_visible_students(
            enrollments.student_id.with_context(active_test=False)
        )
        rows = students._grid_rows()
        scales = {}
        for row in rows:
            scale = section._get_grading_scale(students.browse(row["id"]))
            row["scale_id"] = scale.id
            if scale and scale.id not in scales:
                scales[scale.id] = [
                    {"letter": line.letter, "min": line.min_percent, "value": line.entry_percent}
                    for line in scale.line_ids.sorted("min_percent", reverse=True)
                ]
        result["students"] = rows
        result["scales"] = scales
        result["comments"] = {
            mark.student_id.id: mark.comment
            for mark in self.env["school.period.mark"].search([
                ("section_id", "=", section.id), ("period_id", "=", period.id),
                ("student_id", "in", students.ids), ("comment", "!=", False),
            ])
        }
        result["scores"] = [
            score._cell()
            for score in self.env["school.score"].search([("assignment_id", "in", assignments.ids)])
        ]
        result.update(section._gradebook_grades(period, students))
        return result

    def _gradebook_visible_students(self, students):
        """A homeroom teacher who doesn't teach the class sees only their
        own homeroom's students in it (the others' scores are closed)."""
        self.ensure_one()
        user = self.env.user
        if user in (self.teacher_id | self.co_teacher_ids) or user.has_group(
            "horizonforge_school_core.group_school_office"
        ):
            return students
        return students.filtered(lambda s: s.homeroom_id.teacher_id == user)

    def _gradebook_grades(self, period, students=None):
        """The grid's grade column: each student's period grade and
        category averages, and the class average."""
        self.ensure_one()
        Engine = self.env["school.grade.engine"]
        if students is None:
            students = self.enrollment_ids.student_id.with_context(active_test=False)
        grades = Engine._section_grades(self, period, students)
        _method, weights = Engine._weights(self)
        return {
            "grades": {
                student_id: {
                    "grade": Engine._format(grade["grade"]),
                    "letter": grade["letter"],
                    "categories": {
                        category_id: Engine._format(average, self.env.company.school_display_decimals)
                        for category_id, average in grade["categories"].items()
                    },
                }
                for student_id, grade in grades.items()
            },
            "class_average": Engine._format(
                Engine._class_average(grades), self.env.company.school_display_decimals
            ),
            # Categories that count, in order: the columns of category averages.
            "weights": {
                category.id: weights.get(category.id, 0.0)
                for category in self.env["school.score.category"].search([])
                if weights is not None and weights.get(category.id)
            },
        }

    def gradebook_set_comment(self, period_id, student_id, comment):
        """Save a student's report card comment for the grading period,
        from the grid's Comments column."""
        self.ensure_one()
        period = self.env["school.period"].browse(period_id)
        if not self._gradebook_can_edit(period):
            raise AccessError(_("You can't change this class's comments for %(period)s.", period=period.name))
        Mark = self.env["school.period.mark"]
        mark = Mark.search([
            ("section_id", "=", self.id), ("period_id", "=", period.id), ("student_id", "=", student_id),
        ], limit=1)
        comment = (comment or "").strip() or False
        if mark:
            mark.comment = comment
        elif comment:
            Mark.create({
                "section_id": self.id, "period_id": period.id, "student_id": student_id, "comment": comment,
            })
        return comment or ""

    @api.model
    def gradebook_set_cell_letters(self, show):
        self.env.user.school_cell_letters = bool(show)
        return True

    @api.model
    def gradebook_set_enter_direction(self, direction):
        self.env.user.school_enter_direction = direction
        return True

    def gradebook_generate(self, period_id):
        """Generate the scheduled assignments from the grid's button."""
        self.ensure_one()
        period = self.env["school.period"].browse(period_id)
        if not self.course_id.assignment_template_ids.filtered("is_scheduled"):
            raise UserError(_(
                "%(course)s has no assignment schedule yet. Add one under "
                "Gradebook, Assignment Schedules.",
                course=self.course_id.name,
            ))
        return len(self._generate_assignments(period))
