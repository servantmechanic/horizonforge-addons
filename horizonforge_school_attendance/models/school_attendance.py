from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError


class SchoolAttendance(models.Model):
    """One line per student and day that wasn't a normal day at school.
    A student without a line is present: only exceptions are recorded."""

    _name = "school.attendance"
    _description = "Attendance"
    _order = "date desc, student_id"

    student_id = fields.Many2one(
        "school.student",
        string="Student",
        required=True,
        ondelete="restrict",
        index=True,
    )
    date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        index=True,
    )
    code_id = fields.Many2one(
        "school.attendance.code",
        string="Code",
        required=True,
        ondelete="restrict",
    )
    note = fields.Char()
    recorded_by = fields.Many2one(
        "res.users",
        string="Recorded By",
        default=lambda self: self.env.user,
        readonly=True,
    )
    homeroom_id = fields.Many2one(
        "school.homeroom",
        string="Homeroom",
        compute="_compute_student_snapshot",
        store=True,
        index=True,
        help="The student's homeroom when the line was recorded: it stays "
             "when the student changes rooms. Who may see the line follows "
             "the student's current homeroom.",
    )
    grade_level_id = fields.Many2one(
        "school.grade.level",
        string="Grade Level",
        compute="_compute_student_snapshot",
        store=True,
        index=True,
        help="The student's grade level when the line was recorded: it stays "
             "when the student moves up a grade.",
    )
    period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        compute="_compute_period_id",
        store=True,
        index=True,
        ondelete="set null",
    )
    kind = fields.Selection(related="code_id.kind", store=True)
    excused = fields.Boolean(related="code_id.excused", store=True)
    absence_days = fields.Float(related="code_id.absence_days", store=True)

    _student_date_unique = models.Constraint(
        "UNIQUE(student_id, date)",
        "A student has one attendance line per day.",
    )

    @api.depends("student_id")
    def _compute_student_snapshot(self):
        # Copied when the line is recorded, not followed afterwards.
        for attendance in self:
            attendance.grade_level_id = attendance.student_id.grade_level_id
            attendance.homeroom_id = attendance.student_id.homeroom_id

    @api.depends("date")
    def _compute_period_id(self):
        Period = self.env["school.period"]
        for attendance in self:
            attendance.period_id = Period._get_for_date(attendance.date) if attendance.date else False

    @api.model
    def action_open_list(self):
        return self.env["school.period"]._school_list_action(
            "horizonforge_school_attendance.school_attendance_action", "my_homeroom")

    @api.depends("student_id", "date", "code_id")
    def _compute_display_name(self):
        for attendance in self:
            attendance.display_name = (
                f"{attendance.student_id.display_name} - {attendance.date} - {attendance.code_id.name}"
            )

    @api.model
    def _year_for(self, date):
        return self.env["school.year"].search(
            [("date_start", "<=", date), ("date_end", ">=", date)], limit=1
        )

    @api.constrains("date")
    def _check_school_day(self):
        for attendance in self:
            year = self._year_for(attendance.date)
            if not year or not year._get_school_days(attendance.date, attendance.date):
                raise ValidationError(_(
                    "%(date)s isn't a school day.", date=fields.Date.to_string(attendance.date)
                ))

    def _check_unlocked(self):
        """Days in a locked grading period only change for administrators."""
        if self.env.su or self.env.user.has_group("horizonforge_school_core.group_school_admin"):
            return
        for date in set(self.mapped("date")):
            period = self.env["school.period"]._get_for_date(date)
            if period.locked:
                raise UserError(_(
                    "%(period)s is locked. Ask the principal to change its attendance.",
                    period=period.display_name,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._check_unlocked()
        return records

    def write(self, vals):
        self._check_unlocked()
        if "code_id" in vals or "note" in vals:
            vals = dict(vals, recorded_by=self.env.user.id)
        res = super().write(vals)
        if "date" in vals:
            self._check_unlocked()
        return res

    def unlink(self):
        self._check_unlocked()
        return super().unlink()

    # ------------------------------------------------------------------
    # Totals
    # ------------------------------------------------------------------

    @api.model
    def _totals(self, students, date_from, date_to):
        """Attendance of ``students`` between two dates (both included).
        School days are counted up to today: tomorrow isn't attended yet."""
        today = fields.Date.context_today(self)
        school_days = 0
        years = self.env["school.year"].search(
            [("date_start", "<=", date_to), ("date_end", ">=", date_from)]
        )
        for year in years:
            school_days += len(year._get_school_days(date_from, min(date_to, today)))
        totals = {
            student.id: {
                "school_days": school_days, "present": float(school_days),
                "absent": 0.0, "excused": 0.0, "unexcused": 0.0, "tardy": 0,
            }
            for student in students
        }
        for attendance in self.search([
            ("student_id", "in", students.ids), ("date", ">=", date_from), ("date", "<=", date_to),
        ]):
            total = totals[attendance.student_id.id]
            if attendance.kind == "tardy":
                total["tardy"] += 1
                continue
            days = attendance.absence_days
            total["absent"] += days
            total["excused" if attendance.excused else "unexcused"] += days
            if attendance.date <= today:
                total["present"] -= days
        return totals

    # ------------------------------------------------------------------
    # Attendance grid
    # ------------------------------------------------------------------

    @api.model
    def _grid_homerooms(self):
        """Homerooms the user takes attendance for: their own, or all for
        the office."""
        domain = []
        if not self.env.user.has_group("horizonforge_school_core.group_school_office"):
            domain = [("teacher_id", "=", self.env.uid)]
        return self.env["school.homeroom"].search(domain)

    @api.model
    def _grid_can_edit(self, homeroom):
        user = self.env.user
        return user.has_group("horizonforge_school_core.group_school_office") or (
            homeroom.teacher_id == user
        )

    def _cell(self):
        self.ensure_one()
        return {
            "student_id": self.student_id.id,
            "date": fields.Date.to_string(self.date),
            "code_id": self.code_id.id,
            "note": self.note or "",
        }

    @api.model
    def attendance_open(self, homeroom_id=False, date=False, mode="week"):
        """Everything the attendance grid needs: one homeroom, and the
        weekdays of a week or of a whole grading period."""
        homerooms = self._grid_homerooms()
        homeroom = self.env["school.homeroom"].browse(homeroom_id).exists() or homerooms[:1]
        today = fields.Date.context_today(self)
        date = fields.Date.to_date(date) if date else today
        result = {
            "homerooms": [{"id": h.id, "name": h.name} for h in homerooms | homeroom],
            "homeroom_id": homeroom.id,
            "today": fields.Date.to_string(today),
            "date": fields.Date.to_string(date),
            "mode": mode,
            "name_order": self.env.user.school_name_order,
            "codes": [
                {"id": c.id, "code": c.code, "name": c.name, "color": c.color, "kind": c.kind}
                for c in self.env["school.attendance.code"].search([])
            ],
            "days": [], "students": [], "records": [], "totals": {},
            "can_edit": False, "period_name": "", "range_label": "",
        }
        if not homeroom:
            return result
        homeroom.check_access("read")
        year = self._year_for(date)
        period = self.env["school.period"]._get_for_date(date)
        if mode == "period" and period:
            first, last = period.date_start, period.date_end
        else:
            first = date - timedelta(days=date.weekday())
            last = first + timedelta(days=4)
        school_days = set(year._get_school_days(first, last)) if year else set()
        days = []
        day = first
        while day <= last:
            if day.weekday() < 5:
                # A day off's name first, else a holiday shown for information.
                off = year.day_off_ids.filtered(
                    lambda d: d.date_start <= day <= d.date_end
                ).sorted(lambda d: d.day_type != "off")[:1]
                days.append({
                    "date": fields.Date.to_string(day),
                    "weekday": day.strftime("%a"),
                    "label": f"{day.month}/{day.day}",
                    "off": day not in school_days,
                    "off_name": off.name or ("" if day in school_days else _("No school")),
                })
            day += timedelta(days=1)
        students = self.env["school.student"].search([("homeroom_id", "=", homeroom.id)])
        records = self.search([
            ("student_id", "in", students.ids), ("date", ">=", first), ("date", "<=", last),
        ])
        # Totals follow the grading period (the year when there is none).
        total_from = period.date_start if period else (year.date_start if year else first)
        total_to = period.date_end if period else (year.date_end if year else last)
        result.update({
            "days": days,
            "students": students._grid_rows(),
            "records": [record._cell() for record in records],
            "totals": self._grid_totals(students, total_from, total_to),
            "total_from": fields.Date.to_string(total_from),
            "total_to": fields.Date.to_string(total_to),
            "can_edit": self._grid_can_edit(homeroom) and not (
                period.locked
                and not self.env.user.has_group("horizonforge_school_core.group_school_admin")
            ),
            "locked": bool(period.locked),
            "period_name": period.name or (year.name if year else ""),
            "range_label": f"{first.strftime('%b')} {first.day} - {last.strftime('%b')} {last.day}, {last.year}",
        })
        return result

    @api.model
    def _grid_totals(self, students, date_from, date_to):
        return {
            student_id: {"absent": f"{total['absent']:g}", "tardy": str(total["tardy"])}
            for student_id, total in self._totals(students, date_from, date_to).items()
        }

    @api.model
    def save_batch(self, changes, total_from=False, total_to=False):
        """Save grid cells. Each change has ``student_id``, ``date``,
        ``code_id`` (False clears the day: the student was present) and
        ``note``. A refused cell doesn't block the others."""
        student_ids = list({change["student_id"] for change in changes})
        dates = list({change["date"] for change in changes})
        existing = {
            (record.student_id.id, fields.Date.to_string(record.date)): record
            for record in self.search([("student_id", "in", student_ids), ("date", "in", dates)])
        }
        saved, errors = [], []
        for change in changes:
            key = (change["student_id"], change["date"])
            record = existing.get(key)
            try:
                with self.env.cr.savepoint():
                    if not change.get("code_id"):
                        if record:
                            record.unlink()
                            existing.pop(key)
                        saved.append({"student_id": key[0], "date": key[1], "code_id": False, "note": ""})
                        continue
                    vals = {"code_id": change["code_id"], "note": change.get("note") or False}
                    if record:
                        record.write(vals)
                    else:
                        record = existing[key] = self.create({
                            "student_id": key[0], "date": key[1], **vals,
                        })
                    saved.append(record._cell())
            except (UserError, ValidationError, AccessError) as error:
                errors.append({
                    "student_id": key[0], "date": key[1],
                    "message": str(error.args[0]) if error.args else str(error),
                })
        totals = {}
        if saved and total_from and total_to:
            students = self.env["school.student"].browse(student_ids).exists()
            totals = self._grid_totals(
                students, fields.Date.to_date(total_from), fields.Date.to_date(total_to)
            )
        return {"saved": saved, "errors": errors, "totals": totals}
