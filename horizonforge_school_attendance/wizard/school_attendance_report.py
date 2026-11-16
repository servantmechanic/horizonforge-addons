import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SchoolAttendanceReport(models.TransientModel):
    _name = "school.attendance.report"
    _description = "Attendance Summary"

    year_id = fields.Many2one(
        "school.year",
        string="School Year",
        default=lambda self: self.env["school.year"]._get_current(),
    )
    period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        domain="[('year_id', '=', year_id)]",
        help="Fills in the dates. Leave empty to type your own.",
    )
    date_from = fields.Date(
        string="From",
        compute="_compute_dates",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
    )
    date_to = fields.Date(
        string="To",
        compute="_compute_dates",
        store=True,
        readonly=False,
        required=True,
        precompute=True,
    )
    homeroom_id = fields.Many2one(
        "school.homeroom",
        string="Homeroom",
    )
    grade_level_id = fields.Many2one(
        "school.grade.level",
        string="Grade Level",
    )
    student_ids = fields.Many2many(
        "school.student",
        string="Students",
        help="Leave empty for every student of the homeroom or grade level, or the whole school.",
    )

    @api.depends("period_id", "year_id")
    def _compute_dates(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            if wizard.period_id:
                wizard.date_from = wizard.period_id.date_start
                wizard.date_to = wizard.period_id.date_end
            elif not wizard.date_from or not wizard.date_to:
                wizard.date_from = wizard.year_id.date_start or today.replace(day=1)
                wizard.date_to = min(wizard.year_id.date_end or today, today) if wizard.year_id else today
                if wizard.date_to < wizard.date_from:
                    wizard.date_to = wizard.year_id.date_end or today

    def _get_students(self):
        self.ensure_one()
        domain = []
        if self.student_ids:
            domain.append(("id", "in", self.student_ids.ids))
        if self.homeroom_id:
            domain.append(("homeroom_id", "=", self.homeroom_id.id))
        if self.grade_level_id:
            domain.append(("grade_level_id", "=", self.grade_level_id.id))
        return self.env["school.student"].search(domain).sorted(
            lambda s: (s.homeroom_id.name or "", (s.last_name or "").lower(), (s.first_name or "").lower())
        )

    def _get_rows(self):
        """One row per student: days present, absent (excused and
        unexcused) and tardies between the dates."""
        self.ensure_one()
        if self.date_to < self.date_from:
            raise UserError(_("The end date is before the start date."))
        students = self._get_students()
        totals = self.env["school.attendance"]._totals(students, self.date_from, self.date_to)
        return [
            {
                "student": student,
                "school_days": totals[student.id]["school_days"],
                "present": f"{totals[student.id]['present']:g}",
                "absent": f"{totals[student.id]['absent']:g}",
                "excused": f"{totals[student.id]['excused']:g}",
                "unexcused": f"{totals[student.id]['unexcused']:g}",
                "tardy": totals[student.id]["tardy"],
            }
            for student in students
        ]

    def action_print(self):
        self.ensure_one()
        if not self._get_rows():
            raise UserError(_("No students for this selection."))
        return self.env.ref(
            "horizonforge_school_attendance.action_report_attendance_summary"
        ).report_action(self)

    def _csv_rows(self):
        header = [_("Student ID"), _("Last Name"), _("First Name"), _("Grade Level"), _("Homeroom"),
                  _("School Days"), _("Present"), _("Absent"), _("Excused"), _("Unexcused"), _("Tardy")]
        rows = [
            [row["student"].student_code or "", row["student"].last_name, row["student"].first_name,
             row["student"].grade_level_id.name or "", row["student"].homeroom_id.name or "",
             row["school_days"], row["present"], row["absent"], row["excused"], row["unexcused"],
             row["tardy"]]
            for row in self._get_rows()
        ]
        return header, rows

    def action_export_csv(self):
        self.ensure_one()
        header, rows = self._csv_rows()
        if not rows:
            raise UserError(_("No students for this selection."))
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        attachment = self.env["ir.attachment"].create({
            "name": f"Attendance {self.date_from} to {self.date_to}.csv",
            "datas": base64.b64encode(buffer.getvalue().encode("utf-8-sig")),
            "mimetype": "text/csv",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "download",
        }
