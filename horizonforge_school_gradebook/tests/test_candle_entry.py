import base64

from freezegun import freeze_time

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestCandleEntry(GradebookCase):
    """Tab past the last column adds the next assignment; a category's key
    changes a column's category; assignments carry notes and files."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Friday 2030-09-06, then Monday the 9th.
        cls.lesson = cls._assignment(name="Lesson 11", date="2030-09-06", sequence=5)
        cls._score(cls.lesson, cls.anna, 90)
        cls.Section = cls.env["school.section"].with_user(cls.teacher)

    def test_default_shortcuts(self):
        self.assertEqual(self.homework.shortcut, "/")
        self.assertEqual(self.test.shortcut, "-")
        with self.assertRaises(ValidationError):
            self.test.shortcut = "t"
        # Set once: a school's own choice stays after an upgrade.
        self.homework.shortcut = "+"
        self.env["school.score.category"]._set_default_shortcuts()
        self.assertEqual(self.homework.shortcut, "+")

    def test_lesson_renamed_once(self):
        self.assertEqual((self.homework.name, self.homework.code), ("Lesson", "L"))
        # A database from before 0.8: renamed on upgrade...
        self.homework.write({"name": "Lesson/Homework", "code": "HW"})
        self.env["school.score.category"]._rename_default_lesson()
        self.assertEqual((self.homework.name, self.homework.code), ("Lesson", "L"))
        # ...but a school's own name stays.
        self.homework.write({"name": "Daily Work", "code": "DW"})
        self.env["school.score.category"]._rename_default_lesson()
        self.assertEqual(self.homework.name, "Daily Work")

    def test_suggest_name(self):
        Assignment = self.env["school.assignment"]
        self.assertEqual(Assignment._suggest_name(self.section_5, self.homework), "Lesson 12")
        # No test yet: the category's name, numbered.
        self.assertEqual(Assignment._suggest_name(self.section_5, self.test), "Test 1")
        # A schedule for the category names it instead.
        self.env["school.assignment.template"].create({
            "course_id": self.math_5.id, "name": "Chapter Test", "category_id": self.test.id,
        })
        self.assertEqual(Assignment._suggest_name(self.section_5, self.test), "Chapter Test 1")
        # A name without a number: numbered by count.
        self._assignment(name="Essay", date="2030-09-03", category_id=self.test.id)
        self.assertEqual(Assignment._suggest_name(self.section_5, self.test), "Essay 2")

    def test_add_next_assignment(self):
        new_id = self.Section.browse(self.section_5.id).gradebook_add_assignment(self.semester_1.id, self.lesson.id)
        new = self.env["school.assignment"].browse(new_id)
        self.assertEqual(new.name, "Lesson 12")
        self.assertEqual(str(new.date), "2030-09-09", "the next school day, after the weekend")
        self.assertEqual(new.category_id, self.homework)
        self.assertEqual(new.sequence, 6)
        # Same points and entry mode as the last of the category.
        spelling = self._assignment(name="Spelling 3", date="2030-09-10", category_id=self.test.id,
                                    entry_mode="wrong", max_points=20)
        new_id = self.Section.browse(self.section_5.id).gradebook_add_assignment(self.semester_1.id, spelling.id)
        new = self.env["school.assignment"].browse(new_id)
        self.assertEqual((new.name, new.entry_mode, new.max_points), ("Spelling 4", "wrong", 20))
        # The period's last day: the same day, after it.
        last = self._assignment(name="Lesson 99", date="2031-01-10")
        new_id = self.Section.browse(self.section_5.id).gradebook_add_assignment(self.semester_1.id, last.id)
        self.assertEqual(str(self.env["school.assignment"].browse(new_id).date), "2031-01-10")

    def test_start_an_empty_period(self):
        section = self.Section.browse(self.section_5.id)
        # Before the period: its first school day; numbering runs on.
        first = self.env["school.assignment"].browse(section.gradebook_add_assignment(self.semester_2.id))
        self.assertEqual((first.name, str(first.date)), ("Lesson 12", "2031-01-13"))
        self.assertEqual(first.period_id, self.semester_2)
        # A category's key in an empty period starts with that category.
        first.unlink()
        test = self.env["school.assignment"].browse(
            section.gradebook_add_assignment(self.semester_2.id, False, self.test.id)
        )
        self.assertEqual(test.name, "Test 1")
        # During the period: the next school day from today.
        test.unlink()
        with freeze_time("2031-02-08"):  # a Saturday
            today = self.env["school.assignment"].browse(section.gradebook_add_assignment(self.semester_2.id))
        self.assertEqual(str(today.date), "2031-02-10")

    def test_first_assignment_of_a_new_class(self):
        """No schedule, no pacing, nothing yet: the first category."""
        section = self.env["school.section"].with_user(self.other_teacher).browse(self.section_6.id)
        new = self.env["school.assignment"].browse(section.gradebook_add_assignment(self.semester_1.id))
        self.assertEqual((new.name, new.category_id), ("Lesson 1", self.homework))
        self.assertEqual((new.entry_mode, new.max_points), ("percent", 100))

    def test_add_needs_rights(self):
        with self.assertRaises(AccessError):
            self.section_5.with_user(self.office).gradebook_add_assignment(self.semester_1.id, self.lesson.id)
        with self.assertRaises(UserError):
            self.Section.browse(self.section_5.id).gradebook_add_assignment(self.semester_2.id, self.lesson.id)

    def test_set_category_renames_grid_names(self):
        section = self.Section.browse(self.section_5.id)
        new = self.env["school.assignment"].browse(section.gradebook_add_assignment(self.semester_1.id, self.lesson.id))
        self.assertEqual(section.gradebook_set_category(new.id, self.test.id), "Test 1")
        self.assertEqual(new.category_id, self.test)
        # And back: it was named by the grid, so it follows again.
        self.assertEqual(section.gradebook_set_category(new.id, self.homework.id), "Lesson 12")
        # A name the teacher chose stays.
        new.name = "Fractions review"
        self.assertEqual(section.gradebook_set_category(new.id, self.test.id), "Fractions review")

    def test_notes_and_files(self):
        file = self.env["ir.attachment"].with_user(self.teacher).create({
            "name": "quiz.pdf", "datas": base64.b64encode(b"%PDF-1.4 quiz"),
        })
        quiz = self.env["school.assignment"].with_user(self.teacher).create({
            "section_id": self.section_5.id, "name": "Quiz 1", "date": "2030-09-04",
            "category_id": self.test.id, "note": "Pages 12-14", "attachment_ids": [(6, 0, file.ids)],
        })
        self.assertEqual((file.res_model, file.res_id), ("school.assignment", quiz.id))
        self.assertEqual(quiz.attachment_count, 1)
        file.with_user(self.teacher).read(["name"])
        with self.assertRaises(AccessError):
            file.with_user(self.other_teacher).read(["name"])
        data = self.Section.gradebook_open(self.section_5.id, self.semester_1.id)
        column = next(a for a in data["assignments"] if a["id"] == quiz.id)
        self.assertEqual((column["note"], column["attachment_count"]), ("Pages 12-14", 1))
        self.assertEqual({c["code"]: c["shortcut"] for c in data["categories"]}["T"], "-")
        self.assertTrue(data["tab_adds_column"])
        with_files = self.env["school.assignment"].search([("attachment_ids", "!=", False)])
        self.assertEqual(with_files, quiz)


@tagged("post_install", "-at_install")
class TestPrincipalGradebookSettings(GradebookCase):

    def test_principal_changes_grading(self):
        principal = self.admin  # School Principal, not a system administrator
        scheme = self.env["school.weight.scheme"].with_user(principal).create({"name": "Tests count more"})
        self.env["school.settings"].with_user(principal).create({
            "school_weight_scheme_id": scheme.id,
            "school_entry_mode": "points",
            "school_card_motto": "Be kind.",
        })
        company = self.env.company
        self.assertEqual(company.school_weight_scheme_id, scheme)
        self.assertEqual(company.school_entry_mode, "points")
        self.assertEqual(company.school_card_motto, "Be kind.")
        arch = self.env["school.settings"].with_user(principal).get_views([(False, "form")])["views"]["form"]["arch"]
        self.assertIn("school_weight_scheme_id", arch)
