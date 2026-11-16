from odoo import fields, models


class SchoolStudent(models.Model):
    _inherit = "school.student"

    attendance_ids = fields.One2many(
        "school.attendance",
        "student_id",
        string="Attendance",
    )

    def _school_attendance_totals(self, date_from, date_to):
        return self.env["school.attendance"]._totals(self, date_from, date_to)
