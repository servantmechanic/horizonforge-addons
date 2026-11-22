from odoo import api, models


class SchoolPeriod(models.Model):
    _inherit = "school.period"

    @api.model_create_multi
    def create(self, vals_list):
        periods = super().create(vals_list)
        periods._school_attendance_reassign()
        return periods

    def write(self, vals):
        result = super().write(vals)
        if {"date_start", "date_end", "year_id"} & set(vals):
            self._school_attendance_reassign()
        return result

    def _school_attendance_reassign(self):
        """Put the attendance lines of these periods' years back in the
        grading period that holds their date, after periods change."""
        Attendance = self.env["school.attendance"].sudo()
        for year in self.year_id:
            lines = Attendance.search([
                ("date", ">=", year.date_start), ("date", "<=", year.date_end),
            ])
            self.env.add_to_compute(Attendance._fields["period_id"], lines)
