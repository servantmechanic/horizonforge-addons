import random

from odoo import api, fields, models


class SchoolYear(models.Model):
    _inherit = "school.year"

    @api.model
    def _load_school_attendance_demo(self):
        """Absences, part days and tardies for the reference school, from
        the start of the year to today. Does nothing without the reference
        school or when attendance already exists.

        By hand: ``env["school.year"]._load_school_attendance_demo()``.
        """
        year = self.search([("name", "=", "2026-27")])
        Attendance = self.env["school.attendance"]
        if not year or Attendance.search_count([], limit=1):
            return
        codes = self.env["school.attendance.code"].search([])
        if not codes:
            return
        by_letter = {code.code: code for code in codes}
        # Mostly present; a few of each kind.
        choices = [letter for letter in "AAEEEHXTTT" if letter in by_letter] or [codes[0].code]
        notes = {"E": ["Doctor's appointment", "Family trip", "Sick, parent called"], "X": ["Dentist"]}
        rng = random.Random(4)
        today = fields.Date.context_today(self)
        students = self.env["school.student"].search([])
        vals_list = []
        for day in year._get_school_days(year.date_start, today):
            for student in students:
                if rng.random() < 0.035:
                    letter = rng.choice(choices)
                    vals_list.append({
                        "student_id": student.id,
                        "date": day,
                        "code_id": by_letter[letter].id,
                        "note": rng.choice(notes[letter]) if letter in notes else False,
                    })
        Attendance.create(vals_list)
