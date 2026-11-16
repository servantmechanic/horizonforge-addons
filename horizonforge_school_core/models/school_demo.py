from datetime import date

from odoo import Command, api, models

FIRST_NAMES = [
    "Anna", "Ben", "Clara", "David", "Emma", "Felix", "Grace", "Henry",
    "Iris", "Jacob", "Kate", "Liam", "Mia", "Noah", "Olivia", "Peter",
    "Quinn", "Rose", "Sam", "Tessa",
]
# Made-up families: the reference school in the spec has no real names.
LAST_NAMES = [
    "Alder", "Birch", "Cedar", "Dogwood", "Elm", "Fir", "Hawthorn", "Juniper",
    "Larch", "Maple", "Oak", "Pine", "Redbud", "Spruce", "Walnut",
]
SUBJECTS = [("Math", "MA"), ("English", "EN"), ("Science", "SC"), ("History", "HI")]
YEAR_START, YEAR_END = date(2026, 8, 24), date(2027, 5, 21)


class SchoolYear(models.Model):
    _inherit = "school.year"

    @api.model
    def _load_school_demo(self):
        """Create the reference school: 10 grade levels, 5 teachers,
        5 homerooms, 60 students and their classes. Does nothing if it is already there.

        Called from the demo data, and by hand on a database without demo
        data: ``env["school.year"]._load_school_demo()``.
        """
        if self.with_context(active_test=False).search_count([("name", "=", "2026-27")]):
            return
        env = self.env
        year = self.create({
            "name": "2026-27",
            "date_start": YEAR_START,
            "date_end": YEAR_END,
            "is_current": True,
            # Six periods of about six weeks, each ending on a Friday.
            "period_ids": self._period_vals(YEAR_START, YEAR_END, 6, "Period"),
        })
        levels = env["school.grade.level"].create([
            {"name": f"Grade {number}", "sequence": number} for number in range(1, 11)
        ])
        teacher_group = env.ref("horizonforge_school_core.group_school_teacher")
        teachers = env["res.users"].with_context(no_reset_password=True).create([
            {
                "name": f"Teacher {LAST_NAMES[-number]}",
                "login": f"teacher{number}",
                "password": "teacher",
                "group_ids": [Command.link(env.ref("base.group_user").id), Command.link(teacher_group.id)],
            }
            for number in range(1, 6)
        ])

        env["school.homeroom"].create([
            {
                "name": f"Grades {2 * number - 1}-{2 * number}",
                "teacher_id": teachers[number - 1].id,
                "capacity": 16,
                "grade_level_ids": [Command.set(levels[2 * number - 2:2 * number].ids)],
            }
            for number in range(1, 6)
        ])
        env["school.calendar.day"].create([
            {"year_id": year.id, "name": name, "date_start": start, "date_end": end}
            for name, start, end in [
                ("Labor Day", date(2026, 9, 7), date(2026, 9, 7)),
                ("Teacher work day", date(2026, 10, 9), date(2026, 10, 9)),
                ("Thanksgiving break", date(2026, 11, 26), date(2026, 11, 27)),
                ("Christmas break", date(2026, 12, 21), date(2027, 1, 1)),
                ("Spring break", date(2027, 3, 15), date(2027, 3, 19)),
            ]
        ])
        if not env.company.school_principal_name:
            env.company.school_principal_name = "Dr. Hazel Sycamore"
        # An office login, beside the teachers'.
        env["res.users"].with_context(no_reset_password=True).create({
            "name": "Olive Office",
            "login": "office",
            "password": "office",
            "group_ids": [
                Command.link(env.ref("base.group_user").id),
                Command.link(env.ref("horizonforge_school_core.group_school_office").id),
            ],
        })

        # 12 families of 5 children, spread over the grade levels.
        patrons = env["res.partner"]
        student_vals = []
        for family, last_name in enumerate(LAST_NAMES[:12]):
            parents = env["res.partner"].create([
                {
                    "name": f"{first_name} {last_name}",
                    "is_patron": True,
                    "relationship": relationship,
                    "street": f"{100 + family} Orchard Road",
                    "city": "Springfield",
                }
                for first_name, relationship in (("Mary", "mother"), ("John", "father"))
            ])
            patrons |= parents
            for child in range(5):
                index = family * 5 + child
                level = index % 10
                student_vals.append({
                    "first_name": FIRST_NAMES[(family * 3 + child * 4) % len(FIRST_NAMES)],
                    "last_name": last_name,
                    "student_code": str(1001 + index),
                    "grade_level_id": levels[level].id,
                    "birthdate": date(2020 - level, 1 + index % 12, 1 + index % 28),
                    "patron_ids": [Command.set(parents.ids)],
                    "street": parents[0].street,
                    "city": parents[0].city,
                })
        env["school.student"].create(student_vals)

        for number in range(1, 11):
            env["school.course"].create([
                {
                    "name": f"{subject} {number}",
                    "code": f"{code}{number}",
                    "sequence": sequence * 10,
                    "grade_level_ids": [Command.set(levels[number - 1].ids)],
                }
                for sequence, (subject, code) in enumerate(SUBJECTS, start=1)
            ])
        # One class per course of each homeroom's grade levels, students enrolled.
        year.action_generate_sections()
