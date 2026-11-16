from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestGradebookGrid(GradebookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.lesson = cls._assignment(name="Lesson 1", date="2030-09-03")
        cls.quiz = cls._assignment(name="Quiz", date="2030-09-05", entry_mode="points", max_points=20)
        cls.later = cls._assignment(name="Lesson 40", date="2031-02-03")
        cls._score(cls.lesson, cls.anna, 91, comment="Late")
        cls.Section = cls.env["school.section"].with_user(cls.teacher)
        cls.Score = cls.env["school.score"].with_user(cls.teacher)

    def _change(self, assignment, student, status="scored", value=False, comment=""):
        return {
            "assignment_id": assignment.id, "student_id": student.id,
            "status": status, "value": value, "comment": comment,
        }

    def test_open_default_class_and_period(self):
        data = self.Section.gradebook_open()
        self.assertEqual(data["section_id"], self.section_5.id)
        self.assertEqual([s["id"] for s in data["sections"]], self.section_5.ids)
        self.assertEqual([p["name"] for p in data["periods"]], ["Semester 1", "Semester 2"])
        # Today is before the test year: the first period that hasn't started.
        self.assertEqual(data["period_id"], self.semester_1.id)
        self.assertTrue(data["can_edit"])
        self.assertEqual(data["entry_mode"], "percent")
        self.assertEqual(data["enter_direction"], "down")
        self.assertEqual([a["name"] for a in data["assignments"]], ["Lesson 1", "Quiz"])
        self.assertEqual([s["name"] for s in data["students"]], ["Example, Anna", "Example, Ben"])
        self.assertEqual(data["scores"], [{
            "assignment_id": self.lesson.id, "student_id": self.anna.id,
            "value": 91.0, "status": "scored", "comment": "Late", "percent": 91.0,
        }])
        self.assertEqual({c["code"] for c in data["categories"]} >= {"HW", "T"}, True)

    def test_open_other_period(self):
        data = self.Section.gradebook_open(self.section_5.id, self.semester_2.id)
        self.assertEqual([a["name"] for a in data["assignments"]], ["Lesson 40"])

    def test_students_by_enrollment_dates(self):
        enrollment = self.section_5.enrollment_ids.filtered(lambda e: e.student_id == self.ben)
        enrollment.date_end = "2030-10-01"  # Ben left during semester 1
        first = self.Section.gradebook_open(self.section_5.id, self.semester_1.id)
        second = self.Section.gradebook_open(self.section_5.id, self.semester_2.id)
        self.assertEqual(len(first["students"]), 2)
        self.assertEqual([s["name"] for s in second["students"]], ["Example, Anna"])

    def test_open_without_classes(self):
        self.section_5.teacher_id = self.other_teacher
        data = self.Section.gradebook_open()
        self.assertEqual(data["sections"], [])
        self.assertFalse(data["section_id"])

    def test_open_other_teachers_class_refused(self):
        with self.assertRaises(AccessError):
            self.Section.gradebook_open(self.section_6.id)

    def test_office_reads_all_classes(self):
        data = self.env["school.section"].with_user(self.office).gradebook_open(self.section_6.id)
        self.assertFalse(data["can_edit"])
        self.assertEqual(
            {s["id"] for s in data["sections"]} >= set((self.section_5 | self.section_6).ids), True
        )

    def test_locked_period_is_read_only(self):
        self.semester_1.locked = True
        data = self.Section.gradebook_open(self.section_5.id, self.semester_1.id)
        self.assertFalse(data["can_edit"])
        self.assertTrue(data["locked"])
        admin_data = self.env["school.section"].with_user(self.admin).gradebook_open(
            self.section_5.id, self.semester_1.id
        )
        self.assertTrue(admin_data["can_edit"])

    def test_save_batch(self):
        result = self.Score.save_batch([
            self._change(self.lesson, self.anna, value=95, comment="Late"),  # update
            self._change(self.lesson, self.ben, value=80),                   # create
            self._change(self.quiz, self.anna, value=15),                    # points: 15 of 20
            self._change(self.quiz, self.ben, status="excused"),
        ])
        self.assertFalse(result["errors"])
        saved = {(c["assignment_id"], c["student_id"]): c for c in result["saved"]}
        self.assertEqual(saved[self.lesson.id, self.anna.id]["percent"], 95)
        self.assertEqual(saved[self.quiz.id, self.anna.id]["percent"], 75)
        self.assertEqual(saved[self.quiz.id, self.ben.id]["status"], "excused")
        scores = self.env["school.score"].search([("section_id", "=", self.section_5.id)])
        self.assertEqual(len(scores), 4)
        self.assertEqual(self.lesson.score_ids.filtered(lambda s: s.student_id == self.anna).comment, "Late")

    def test_save_batch_clear(self):
        result = self.Score.save_batch([
            self._change(self.lesson, self.anna, status=False),
            self._change(self.lesson, self.ben, status=False),  # already empty: fine
        ])
        self.assertFalse(result["errors"])
        self.assertEqual([c["status"] for c in result["saved"]], [False, False])
        self.assertFalse(self.lesson.score_ids)

    def test_save_batch_bad_cell_does_not_block_others(self):
        result = self.Score.save_batch([
            self._change(self.lesson, self.ben, value=120),   # over 100
            self._change(self.quiz, self.ben, value=18),
            self._change(self.quiz, self.carl, value=10),     # not enrolled
        ])
        self.assertEqual(len(result["saved"]), 1)
        self.assertEqual(
            [(e["assignment_id"], e["student_id"]) for e in result["errors"]],
            [(self.lesson.id, self.ben.id), (self.quiz.id, self.carl.id)],
        )
        self.assertIn("0 to 100", result["errors"][0]["message"])
        self.assertEqual(self.quiz.score_ids.value_entered, 18)
        self.assertEqual(len(self.lesson.score_ids), 1)

    def test_save_batch_other_teachers_class(self):
        other = self._assignment(section=self.section_6, name="Other")
        result = self.Score.save_batch([self._change(other, self.carl, value=90)])
        self.assertFalse(result["saved"])
        self.assertEqual(len(result["errors"]), 1)
        self.assertFalse(other.score_ids)

    def test_save_batch_locked(self):
        self.semester_1.locked = True
        result = self.Score.save_batch([self._change(self.lesson, self.anna, value=50)])
        self.assertIn("locked", result["errors"][0]["message"])
        self.assertEqual(self.lesson.score_ids.value_entered, 91)

    def test_save_batch_deleted_assignment(self):
        change = self._change(self.quiz, self.anna, value=10)
        self.quiz.unlink()
        result = self.Score.save_batch([change])
        self.assertEqual(len(result["errors"]), 1)

    def test_enter_direction_preference(self):
        self.Section.gradebook_set_enter_direction("right")
        self.assertEqual(self.teacher.school_enter_direction, "right")
        self.assertEqual(self.Section.gradebook_open()["enter_direction"], "right")

    def test_generate_from_grid(self):
        self.env["school.assignment.template"].create({
            "course_id": self.math_5.id, "name": "Drill", "category_id": self.homework.id,
            "friday": True,
        })
        self.semester_1.date_end = "2030-09-13"
        count = self.section_5.with_user(self.teacher).gradebook_generate(self.semester_1.id)
        self.assertEqual(count, 3)
        self.assertTrue(self.Section.gradebook_open()["has_schedule"])
