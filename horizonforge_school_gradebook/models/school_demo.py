import random

from odoo import api, fields, models


class SchoolYear(models.Model):
    _inherit = "school.year"

    @api.model
    def _load_school_gradebook_demo(self):
        """Schedules for the reference school's courses, the started quarters'
        assignments and scores up to today. Does nothing without the
        reference school or when schedules already exist.

        By hand: ``env["school.year"]._load_school_gradebook_demo()``.
        """
        year = self.search([("name", "=", "2026-27")])
        Template = self.env["school.assignment.template"]
        if not year or Template.search_count([], limit=1):
            return
        homework = self.env.ref("horizonforge_school_gradebook.score_category_homework")
        test = self.env.ref("horizonforge_school_gradebook.score_category_test")
        every_day = dict.fromkeys(["monday", "tuesday", "wednesday", "thursday", "friday"], True)
        vals_list = []
        for course in year.section_ids.course_id:
            subject = course.name.split()[0]
            if subject == "Math":
                vals_list.append({"course_id": course.id, "name": "Lesson", "category_id": homework.id, **every_day})
                vals_list.append({"course_id": course.id, "name": "Test", "category_id": test.id,
                                  "friday": True, "sequence": 20, "week_interval": 2, "first_week": 2})
            elif subject == "English":
                vals_list.append({"course_id": course.id, "name": "Lesson", "category_id": homework.id,
                                  "monday": True, "wednesday": True, "friday": True})
                vals_list.append({"course_id": course.id, "name": "Spelling Test", "category_id": test.id,
                                  "friday": True, "sequence": 20, "entry_mode": "wrong", "max_points": 20})
                # A writing assignment graded by letter every other week.
                vals_list.append({"course_id": course.id, "name": "Writing", "category_id": homework.id,
                                  "wednesday": True, "sequence": 30, "entry_mode": "letter",
                                  "week_interval": 2, "first_week": 1})
            elif subject == "Science":
                vals_list.append({"course_id": course.id, "name": "Lesson", "category_id": homework.id,
                                  "tuesday": True, "thursday": True})
                vals_list.append({"course_id": course.id, "name": "Quiz", "category_id": test.id,
                                  "thursday": True, "sequence": 20, "entry_mode": "points", "max_points": 25,
                                  "week_interval": 3, "first_week": 3})
            else:
                vals_list.append({"course_id": course.id, "name": "Lesson", "category_id": homework.id,
                                  "tuesday": True, "thursday": True})
        Template.create(vals_list)
        self._load_school_gradebook_demo_extras(year)

        today = fields.Date.context_today(self)
        assignments = self.env["school.assignment"]
        # The periods already started, or the first one before the year starts.
        for period in year.period_ids.filtered(lambda p: p.date_start <= today) or year.period_ids[:1]:
            assignments |= year.section_ids._generate_assignments(period)
        rng = random.Random(19)
        score_vals = []
        for assignment in assignments.filtered(lambda a: a.date <= today):
            for student in assignment.section_id.enrollment_ids.student_id:
                roll = rng.random()
                if roll < 0.03:
                    score_vals.append({"assignment_id": assignment.id, "student_id": student.id,
                                       "status": "missing"})
                    continue
                if assignment.entry_mode == "letter":
                    letters = assignment.section_id._get_grading_scale(student).line_ids.sorted(
                        "min_percent", reverse=True).mapped("letter")
                    score_vals.append({"assignment_id": assignment.id, "student_id": student.id,
                                       "letter_entered": rng.choice(letters[:3]) if letters else "A"})
                    continue
                if assignment.entry_mode == "wrong":
                    value = rng.choice([0, 0, 1, 1, 2, 3, 4])
                elif assignment.entry_mode == "points":
                    value = rng.randint(17, 25)
                else:
                    value = rng.randint(70, 100)
                score_vals.append({"assignment_id": assignment.id, "student_id": student.id,
                                   "value_entered": value})
        self.env["school.score"].create(score_vals)

    @api.model
    def _load_school_gradebook_demo_extras(self, year):
        """What a trial should show beside scores: a lower-grades scale,
        courses graded by letters (PE, with its schedule) or by comment,
        report card comments, and printing that works the first time."""
        env = self.env
        company = env.company
        if not company.external_report_layout_id:
            company.external_report_layout_id = env.ref("web.external_layout_standard")
        esnu = env.ref("horizonforge_school_gradebook.grading_scale_esnu", raise_if_not_found=False)
        levels = env["school.grade.level"].search([("name", "in", ["Grade 1", "Grade 2"])])
        if esnu:
            levels.grading_scale_id = esnu

        # PE by letter and Conduct by comment, for every grade level.
        for level in env["school.grade.level"].search([("name", "like", "Grade ")]):
            number = level.name.split()[-1]
            env["school.course"].create([
                {"name": f"PE {number}", "code": f"PE{number}", "sequence": 50,
                 "grading_type": "letter", "grade_level_ids": [(6, 0, level.ids)]},
                {"name": f"Conduct {number}", "code": f"CO{number}", "sequence": 60,
                 "grading_type": "comment", "grade_level_ids": [(6, 0, level.ids)]},
            ])
        year.action_generate_sections()
        homework = env.ref("horizonforge_school_gradebook.score_category_homework")
        env["school.assignment.template"].create([
            {"course_id": course.id, "name": "Activity", "category_id": homework.id,
             "tuesday": True, "thursday": True}
            for course in env["school.course"].search([("grading_type", "=", "letter")])
        ])

        today = fields.Date.context_today(self)
        finished = year.period_ids.filtered(lambda p: p.date_end < today)
        rng = random.Random(7)
        conduct = [
            "Kind and helpful to classmates.", "Listens well and follows directions.",
            "Works hard; reminders needed to stay on task.", "A cheerful, respectful student.",
            "Is learning to wait for a turn to speak.",
        ]
        math = [
            "Careful, accurate work this period.", "Should review multiplication facts at home.",
            "Great improvement on tests.", "Please check that homework is finished each night.",
        ]
        vals_list = []
        for section in year.section_ids:
            kind = section.grading_type
            subject = section.course_id.name.split()[0]
            for period in finished:
                for student in section.enrollment_ids.student_id:
                    vals = {"section_id": section.id, "student_id": student.id, "period_id": period.id}
                    if kind == "comment":
                        vals["comment"] = rng.choice(conduct)
                    elif subject == "Math" and rng.random() < 0.5:
                        vals["comment"] = rng.choice(math)
                    else:
                        continue
                    vals_list.append(vals)
        env["school.period.mark"].create(vals_list)
