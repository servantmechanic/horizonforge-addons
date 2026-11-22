from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestGradebookSecurity(GradebookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.mine = cls._assignment()
        cls.theirs = cls._assignment(section=cls.section_6)
        cls.my_score = cls._score(cls.mine, cls.anna, 90)
        cls.their_score = cls._score(cls.theirs, cls.carl, 70)

    def test_teacher_own_classes_only(self):
        Assignment = self.env["school.assignment"].with_user(self.teacher)
        Score = self.env["school.score"].with_user(self.teacher)
        self.assertEqual(Assignment.search([("section_id.year_id", "=", self.year.id)]), self.mine)
        self.assertEqual(Score.search([("section_id.year_id", "=", self.year.id)]), self.my_score)
        with self.assertRaises(AccessError):
            self.their_score.with_user(self.teacher).read(["percent"])
        with self.assertRaises(AccessError):
            self.their_score.with_user(self.teacher).value_entered = 100
        with self.assertRaises(AccessError):
            self.theirs.with_user(self.teacher).name = "Changed"
        with self.assertRaises(AccessError):
            Assignment.create({
                "section_id": self.section_6.id, "name": "Sneaky", "date": "2030-09-03",
                "category_id": self.homework.id,
            })
        self.my_score.with_user(self.teacher).value_entered = 95
        self.mine.with_user(self.teacher).unlink()

    def test_co_teacher_grades(self):
        self.section_6.co_teacher_ids = self.teacher
        self.their_score.with_user(self.teacher).value_entered = 75
        self.assertEqual(self.their_score.value_entered, 75)

    def test_office_reads_all_edits_none(self):
        scores = self.env["school.score"].with_user(self.office).search(
            [("section_id.year_id", "=", self.year.id)]
        )
        self.assertEqual(scores, self.my_score | self.their_score)
        with self.assertRaises(AccessError):
            self.my_score.with_user(self.office).value_entered = 100
        with self.assertRaises(AccessError):
            self.mine.with_user(self.office).unlink()

    def test_admin_edits_all(self):
        self.their_score.with_user(self.admin).value_entered = 99
        self.theirs.with_user(self.admin).unlink()

    def test_teacher_reads_configuration_only(self):
        with self.assertRaises(AccessError):
            self.homework.with_user(self.teacher).name = "Changed"
        with self.assertRaises(AccessError):
            self.env.company.school_weight_scheme_id.with_user(self.teacher).name = "Changed"

    def test_teacher_manages_own_course_schedules(self):
        Template = self.env["school.assignment.template"]
        vals = {"name": "Lesson", "category_id": self.homework.id, "monday": True}
        mine = Template.with_user(self.teacher).create({"course_id": self.math_5.id, **vals})
        mine.friday = True
        theirs = Template.create({"course_id": self.math_6.id, **vals})
        self.assertIn(theirs, Template.with_user(self.teacher).search([]))  # everyone reads them
        with self.assertRaises(AccessError):
            theirs.with_user(self.teacher).friday = True
        with self.assertRaises(AccessError):
            theirs.with_user(self.teacher).unlink()
        with self.assertRaises(AccessError):
            Template.with_user(self.teacher).create({"course_id": self.math_6.id, **vals})
        mine.unlink()
        theirs.with_user(self.admin).friday = True
