from freezegun import freeze_time

from odoo.exceptions import AccessError
from odoo.tests import new_test_user, tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestHomeroomAccess(GradebookCase):
    """The homeroom teacher keeps their students' grades in classes other
    teachers teach, beside those teachers, and prints their report cards."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Anna is in other_teacher's homeroom; teacher teaches her Math 5.
        cls.homeroom = cls.env["school.homeroom"].create({
            "name": "Test Homeroom", "teacher_id": cls.other_teacher.id,
        })
        cls.anna.homeroom_id = cls.homeroom
        cls.third_teacher = new_test_user(
            cls.env, login="school_teacher_3",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        cls.lesson = cls._assignment(name="Lesson 1", date="2030-09-03")
        cls.anna_score = cls._score(cls.lesson, cls.anna, 90)
        cls.ben_score = cls._score(cls.lesson, cls.ben, 80)
        cls.env["school.period.mark"].create({
            "section_id": cls.section_5.id, "student_id": cls.anna.id,
            "period_id": cls.semester_1.id, "comment": "Works hard",
        })

    def test_reads_homeroom_students_grades(self):
        env = self.env(user=self.other_teacher)
        self.assertIn(self.section_5, env["school.section"].search([]))
        self.assertEqual(env["school.assignment"].search([("section_id", "=", self.section_5.id)]), self.lesson)
        scores = env["school.score"].search([("section_id", "=", self.section_5.id)])
        self.assertEqual(scores, self.anna_score, "only the homeroom's students")
        marks = env["school.period.mark"].search([("section_id", "=", self.section_5.id)])
        self.assertEqual(marks.comment, "Works hard")

    def test_enters_homeroom_students_grades(self):
        self.anna_score.with_user(self.other_teacher).value_entered = 100
        self.assertEqual(self.anna_score.percent, 100)
        quiz = self.env["school.assignment"].with_user(self.other_teacher).create({
            "section_id": self.section_5.id, "name": "Quiz", "date": "2030-09-04",
            "category_id": self.homework.id,
        })
        result = self.env["school.score"].with_user(self.other_teacher).save_batch([
            {"assignment_id": quiz.id, "student_id": self.anna.id, "status": "scored", "value": 88},
            {"assignment_id": quiz.id, "student_id": self.ben.id, "status": "scored", "value": 77},
        ])
        self.assertEqual([c["student_id"] for c in result["saved"]], self.anna.ids)
        self.assertEqual([e["student_id"] for e in result["errors"]], self.ben.ids, "not their homeroom")
        # The class's own teacher still enters everyone's.
        self.anna_score.with_user(self.teacher).value_entered = 95

    def test_grid_lists_homeroom_classes(self):
        Section = self.env["school.section"].with_user(self.other_teacher)
        data = Section.gradebook_open(self.section_5.id, self.semester_1.id)
        self.assertIn(self.section_5.id, [s["id"] for s in data["sections"]])
        self.assertTrue(data["can_edit"])
        self.assertEqual([s["name"] for s in data["students"]], ["Example, Anna"])
        mine = self.env["school.section"].with_user(self.other_teacher).search(
            self.env["school.section"]._my_classes_domain(self.other_teacher)
        )
        self.assertEqual(mine, self.section_5 | self.section_6)

    def test_other_homeroom_stays_closed(self):
        with self.assertRaises(AccessError):
            self.ben_score.with_user(self.other_teacher).read(["percent"])
        with self.assertRaises(AccessError):
            self.lesson.with_user(self.third_teacher).name = "Changed"

    def test_report_card_with_every_subject(self):
        Wizard = self.env["school.grade.report"].with_user(self.other_teacher)
        wizard = Wizard.create({
            "year_id": self.year.id, "period_id": self.semester_1.id, "homeroom_id": self.homeroom.id,
        })
        card, = wizard._get_report_cards()
        self.assertEqual(card["student"], self.anna)
        self.assertEqual([row["course"] for row in card["rows"]], ["Test Math 5"])


@tagged("post_install", "-at_install")
class TestGradebookTeacherFeedback(GradebookCase):

    def test_duplicate_course_copies_schedule(self):
        self.env["school.assignment.template"].create({
            "course_id": self.math_5.id, "name": "Lesson", "category_id": self.homework.id,
            "monday": True, "friday": True,
        })
        copy = self.math_5.copy()
        self.assertEqual(copy.assignment_template_ids.mapped("name"), ["Lesson"])
        self.assertTrue(copy.assignment_template_ids.friday)
        self.assertEqual(len(self.math_5.assignment_template_ids), 1)

    def test_current_period_for_the_banner(self):
        Section = self.env["school.section"].with_user(self.teacher)
        with freeze_time("2030-12-02"):
            data = Section.gradebook_open(self.section_5.id, self.semester_2.id)
        self.assertEqual(data["period_id"], self.semester_2.id)
        self.assertEqual(data["current_period_id"], self.semester_1.id)
        # Before the year starts there is no current period.
        self.assertFalse(Section.gradebook_open(self.section_5.id)["current_period_id"])

    def test_school_default_enter_direction(self):
        self.env.company.school_enter_direction = "right"
        user = new_test_user(
            self.env, login="school_new_teacher",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        self.assertEqual(user.school_enter_direction, "right")
