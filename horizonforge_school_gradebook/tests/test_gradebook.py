from datetime import date

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestGradebook(GradebookCase):

    # Configuration

    def test_shipped_defaults(self):
        company = self.env.company
        self.assertEqual(company.school_weight_scheme_id.line_ids.mapped("weight"), [50, 50])
        scale = company.school_grading_scale_id
        self.assertEqual(
            [scale._get_letter(p) for p in (100, 93, 92, 85, 77, 70, 69, 0)],
            ["A", "A", "B", "B", "C", "D", "F", "F"],
        )

    def test_weights_total_100(self):
        with self.assertRaises(ValidationError):
            self.env["school.weight.scheme"].create({
                "name": "Bad",
                "line_ids": [
                    Command.create({"category_id": self.homework.id, "weight": 40}),
                    Command.create({"category_id": self.test.id, "weight": 50}),
                ],
            })
        scheme = self.env["school.weight.scheme"].create({
            "name": "Thirds",
            "line_ids": [
                Command.create({"category_id": self.homework.id, "weight": 33.33}),
                Command.create({"category_id": self.test.id, "weight": 66.67}),
            ],
        })
        with self.assertRaises(ValidationError):
            scheme.write({"line_ids": [Command.update(scheme.line_ids[0].id, {"weight": 10})]})
        # Both lines changed in one save: only the total matters.
        scheme.write({"line_ids": [
            Command.update(scheme.line_ids[0].id, {"weight": 40}),
            Command.update(scheme.line_ids[1].id, {"weight": 60}),
        ]})

    def test_settings_resolve_most_specific_first(self):
        section = self.section_5
        school_scheme = self.env.company.school_weight_scheme_id
        course_scheme = school_scheme.copy({"name": "Course"})
        class_scheme = school_scheme.copy({"name": "Class"})
        self.assertEqual(section._get_weight_scheme(), school_scheme)
        section.course_id.weight_scheme_id = course_scheme
        self.assertEqual(section._get_weight_scheme(), course_scheme)
        section.weight_scheme_id = class_scheme
        self.assertEqual(section._get_weight_scheme(), class_scheme)

        self.assertEqual(section._get_entry_mode(), "percent")
        self.env.company.school_entry_mode = "points"
        self.assertEqual(section._get_entry_mode(), "points")
        section.entry_mode = "wrong"
        self.assertEqual(section._get_entry_mode(), "wrong")

        school_scale = self.env.company.school_grading_scale_id
        level_scale = school_scale.copy({"name": "Lower grades"})
        course_scale = school_scale.copy({"name": "Course"})
        self.assertEqual(section._get_grading_scale(self.anna), school_scale)
        self.level_5.grading_scale_id = level_scale
        self.assertEqual(section._get_grading_scale(self.anna), level_scale)
        section.course_id.grading_scale_id = course_scale
        self.assertEqual(section._get_grading_scale(self.anna), course_scale)

    def test_settings_form(self):
        settings = self.env["res.config.settings"].create({})
        settings.school_entry_mode = "points"
        settings.execute()
        self.assertEqual(self.env.company.school_entry_mode, "points")

    # Assignments

    def test_assignment_period_from_date(self):
        assignment = self._assignment()
        self.assertEqual(assignment.period_id, self.semester_1)
        self.assertEqual(assignment.entry_mode, "percent")
        assignment.date = "2031-02-03"
        self.assertEqual(assignment.period_id, self.semester_2)
        with self.assertRaises(UserError):
            assignment.date = "2031-01-11"  # between the two semesters
        with self.assertRaises(UserError):
            self._assignment(date="2031-06-30")

    def test_assignment_entry_mode_from_class(self):
        self.section_5.entry_mode = "points"
        assignment = self._assignment(max_points=25)
        self.assertEqual(assignment.entry_mode, "points")
        self.assertEqual(self._assignment(entry_mode="wrong").entry_mode, "wrong")

    def test_assignment_max_points_positive(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self._assignment(max_points=0)

    # Scores

    def test_percent_by_entry_mode(self):
        cases = [("percent", 100, 88, 88), ("points", 25, 22, 88), ("wrong", 25, 3, 88)]
        for mode, max_points, typed, percent in cases:
            assignment = self._assignment(entry_mode=mode, max_points=max_points)
            score = self._score(assignment, self.anna, typed)
            self.assertAlmostEqual(score.percent, percent, msg=mode)
            self.assertEqual(score.value_entered, typed)

    def test_max_points_change_recalculates(self):
        assignment = self._assignment(entry_mode="points", max_points=25)
        score = self._score(assignment, self.anna, 20)
        self.assertAlmostEqual(score.percent, 80)
        assignment.max_points = 40
        self.assertAlmostEqual(score.percent, 50)
        self.assertEqual(score.value_entered, 20)
        assignment.entry_mode = "wrong"
        self.assertAlmostEqual(score.percent, 50)
        with self.assertRaises(ValidationError):
            assignment.max_points = 10

    def test_score_range(self):
        percent = self._assignment()
        points = self._assignment(entry_mode="points", max_points=25)
        for assignment, bad in ((percent, 101), (percent, -1), (points, 26)):
            with self.assertRaises(ValidationError):
                self._score(assignment, self.anna, bad)
        self._score(percent, self.anna, 100)
        self._score(points, self.anna, 25)

    def test_score_status(self):
        assignment = self._assignment()
        excused = self._score(assignment, self.anna, status="excused")
        missing = self._score(assignment, self.ben, status="missing")
        self.assertEqual(excused.percent, 0)
        self.assertEqual(missing.percent, 0)
        self.assertFalse(excused._cell()["value"])

    def test_score_unique_and_enrolled(self):
        assignment = self._assignment()
        self._score(assignment, self.anna, 90)
        with self.assertRaises(ValidationError):
            self._score(assignment, self.carl, 90)  # Carl is in the other class
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self._score(assignment, self.anna, 80)

    def test_locked_period(self):
        assignment = self._assignment()
        score = self._score(assignment, self.anna, 90)
        self.semester_1.locked = True
        as_teacher = score.with_user(self.teacher)
        with self.assertRaises(UserError):
            as_teacher.value_entered = 95
        with self.assertRaises(UserError):
            as_teacher.unlink()
        with self.assertRaises(UserError):
            self.env["school.score"].with_user(self.teacher).create({
                "assignment_id": assignment.id, "student_id": self.ben.id, "value_entered": 80,
            })
        with self.assertRaises(UserError):
            assignment.with_user(self.teacher).max_points = 50
        with self.assertRaises(UserError):
            self.env["school.assignment"].with_user(self.teacher).create({
                "section_id": self.section_5.id, "name": "Late", "date": "2030-09-10",
                "category_id": self.homework.id,
            })
        # Moving an assignment into the locked period is refused too.
        open_assignment = self._assignment(date="2031-02-03")
        with self.assertRaises(UserError):
            open_assignment.with_user(self.teacher).date = "2030-09-10"
        score.with_user(self.admin).value_entered = 95
        self.assertEqual(score.value_entered, 95)

    # Schedules

    def _schedule(self, **vals):
        return self.env["school.assignment.template"].create({
            "course_id": self.math_5.id,
            "name": "Lesson",
            "category_id": self.homework.id,
            **vals,
        })

    def test_schedule_needs_a_weekday(self):
        with self.assertRaises(ValidationError):
            self._schedule()

    def test_generate_assignments(self):
        self.env["school.calendar.day"].create({
            "year_id": self.year.id, "name": "Labor Day", "date_start": "2030-09-02",
        })
        self.semester_1.date_end = "2030-09-13"  # three weeks, to keep the numbers small
        self._schedule(monday=True, wednesday=True, friday=True)
        self._schedule(name="Spelling Test", category_id=self.test.id, friday=True,
                       entry_mode="wrong", max_points=20, numbered=False, sequence=20)
        created = self.section_5._generate_assignments(self.semester_1)
        lessons = created.filtered(lambda a: a.category_id == self.homework)
        tests = created - lessons
        self.assertEqual(lessons.mapped("date"), [
            date(2030, 8, 26), date(2030, 8, 28), date(2030, 8, 30),
            date(2030, 9, 4), date(2030, 9, 6),  # no Monday Sep 2: Labor Day
            date(2030, 9, 9), date(2030, 9, 11), date(2030, 9, 13),
        ])
        self.assertEqual(lessons.mapped("name"), [f"Lesson {n}" for n in range(1, 9)])
        self.assertEqual(set(lessons.mapped("entry_mode")), {"percent"})
        self.assertEqual(tests.mapped("date"), [date(2030, 8, 30), date(2030, 9, 6), date(2030, 9, 13)])
        self.assertEqual(set(tests.mapped("name")), {"Spelling Test"})
        self.assertEqual(set(tests.mapped("entry_mode")), {"wrong"})
        self.assertEqual(set(tests.mapped("max_points")), {20})
        self.assertEqual(set(created.mapped("period_id")), {self.semester_1})

        # Running it again adds nothing; a deleted day comes back with its number.
        self.assertFalse(self.section_5._generate_assignments(self.semester_1))
        lessons[2].unlink()
        again = self.section_5._generate_assignments(self.semester_1)
        self.assertEqual(again.mapped("name"), ["Lesson 3"])

        # The numbers carry on into the next grading period.
        self.semester_2.date_end = "2031-01-17"
        later = self.section_5._generate_assignments(self.semester_2)
        first_lesson = later.filtered(lambda a: a.category_id == self.homework)[0]
        self.assertEqual((first_lesson.date, first_lesson.name), (date(2031, 1, 13), "Lesson 9"))

    def test_generate_wizard(self):
        self._schedule(friday=True)
        self.semester_1.date_end = "2030-09-13"
        wizard = self.env["school.assignment.generate"].with_user(self.teacher).create({
            "period_id": self.semester_1.id,
        })
        self.assertEqual(wizard.section_ids, self.section_5)  # only classes with a schedule
        wizard.action_generate()
        self.assertEqual(len(self.section_5.assignment_ids), 3)
        self.assertFalse(self.section_6.assignment_ids)

    def test_new_year_copies_class_settings(self):
        scheme = self.env.company.school_weight_scheme_id.copy({"name": "Class"})
        self.section_5.write({"entry_mode": "points", "weight_scheme_id": scheme.id})
        self._schedule(friday=True)
        wizard = self.env["school.year.setup"].create({"promote_students": False})
        year = self.env["school.year"].browse(wizard.action_confirm()["res_id"])
        section = year.section_ids.filtered(lambda s: s.course_id == self.math_5)
        self.assertEqual(section.entry_mode, "points")
        self.assertEqual(section.weight_scheme_id, scheme)
        # Schedules belong to the course: the new class generates from them.
        created = section._generate_assignments(year.period_ids[0])
        self.assertTrue(created)
        self.assertEqual(created[0].name, "Lesson 1")

    def test_schedule_every_n_weeks(self):
        # Six school weeks from Aug 26; the week of Sep 9 is a break.
        self.semester_1.date_end = "2030-10-11"
        self.env["school.calendar.day"].create({
            "year_id": self.year.id, "name": "Break",
            "date_start": "2030-09-09", "date_end": "2030-09-13",
        })
        weekly = self._schedule(name="Quiz", friday=True)
        every_3 = self._schedule(name="Test", category_id=self.test.id, friday=True,
                                 week_interval=3, first_week=3, sequence=20)
        every_2 = self._schedule(name="Review", thursday=True, week_interval=2, sequence=30)
        created = self.section_5._generate_assignments(self.semester_1)

        def dates(template):
            return created.filtered(lambda a: a.template_id == template).mapped("date")

        self.assertEqual(len(dates(weekly)), 6)
        # School weeks 3 and 6: the break week isn't counted.
        self.assertEqual(dates(every_3), [date(2030, 9, 20), date(2030, 10, 11)])
        self.assertEqual(
            created.filtered(lambda a: a.template_id == every_3).mapped("name"), ["Test 1", "Test 2"]
        )
        # Every other week from week 1: weeks 1, 3 and 5.
        self.assertEqual(dates(every_2), [date(2030, 8, 29), date(2030, 9, 19), date(2030, 10, 3)])
        self.assertFalse(self.section_5._generate_assignments(self.semester_1))
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            every_2.week_interval = 0
            every_2.flush_recordset()
