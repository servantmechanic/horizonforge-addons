from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestPeriodMarks(GradebookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.external_report_layout_id = cls.env.ref("web.external_layout_standard")
        cls.pe = cls.env["school.course"].create({
            "name": "Test PE", "grading_type": "letter", "sequence": 90,
            "grade_level_ids": [(6, 0, cls.level_5.ids)],
        })
        cls.conduct = cls.env["school.course"].create({
            "name": "Test Conduct", "grading_type": "comment", "sequence": 95,
            "grade_level_ids": [(6, 0, cls.level_5.ids)],
        })
        cls.pe_class, cls.conduct_class = cls.env["school.section"].create([
            {"course_id": cls.pe.id, "teacher_id": cls.teacher.id},
            {"course_id": cls.conduct.id, "teacher_id": cls.teacher.id},
        ])
        (cls.pe_class | cls.conduct_class).action_enroll_grade_levels()
        cls.Mark = cls.env["school.period.mark"]

    def _mark(self, section, student, period=None, user=None, **vals):
        return self.Mark.with_user(user or self.teacher).create({
            "section_id": section.id, "student_id": student.id,
            "period_id": (period or self.semester_1).id, **vals,
        })

    def test_entry_mode_per_course(self):
        self.assertEqual(self.section_5._get_entry_mode(), "percent")
        self.math_5.entry_mode = "wrong"
        self.assertEqual(self.section_5._get_entry_mode(), "wrong")
        self.assertEqual(self._assignment().entry_mode, "wrong")
        self.section_5.entry_mode = "points"
        self.assertEqual(self.section_5._get_entry_mode(), "points")

    def test_letter_must_be_in_scale(self):
        mark = self._mark(self.pe_class, self.anna, letter=" b ")
        self.assertEqual(mark.letter, "B")
        with self.assertRaises(ValidationError):
            mark.letter = "Q"
        # The lower grades' scale has its own letters.
        self.level_5.grading_scale_id = self.env.ref("horizonforge_school_gradebook.grading_scale_esnu")
        with self.assertRaises(ValidationError):
            self._mark(self.pe_class, self.ben, letter="B")
        self.assertEqual(self._mark(self.pe_class, self.ben, letter="s").letter, "S")

    def test_open_creates_rows(self):
        action = self.pe_class.with_user(self.teacher).action_open_period_marks()
        marks = self.Mark.search([("section_id", "=", self.pe_class.id)])
        # The year hasn't started: the first period only, a row per student.
        self.assertEqual(marks.mapped("period_id"), self.semester_1)
        self.assertEqual(marks.student_id, self.anna | self.ben)
        self.assertEqual(action["domain"], [("section_id", "in", self.pe_class.ids)])
        self.pe_class.with_user(self.teacher).action_open_period_marks()
        self.assertEqual(self.Mark.search_count([("section_id", "=", self.pe_class.id)]), 2)
        marks[0].with_user(self.teacher).write({"letter": "A", "comment": "Great effort"})

    def test_menu_opens_own_classes(self):
        action = self.Mark.with_user(self.teacher).action_open_marks()
        sections = self.env["school.section"].browse(action["domain"][0][2])
        self.assertEqual(sections, self.section_5 | self.pe_class | self.conduct_class)

    def test_security_and_lock(self):
        mark = self._mark(self.pe_class, self.anna, letter="A")
        with self.assertRaises(AccessError):
            mark.with_user(self.other_teacher).read(["letter"])
        with self.assertRaises(AccessError):
            mark.with_user(self.office).letter = "B"
        self.assertEqual(mark.with_user(self.office).letter, "A")
        self.semester_1.locked = True
        with self.assertRaises(ValidationError):
            mark.with_user(self.teacher).letter = "B"
        mark.with_user(self.admin).letter = "B"

    def test_not_in_the_gradebook(self):
        sections = self.env["school.section"].with_user(self.teacher)._gradebook_sections()
        self.assertEqual(sections, self.section_5)
        self.env["school.assignment.template"].create({
            "course_id": self.pe.id, "name": "Lesson", "category_id": self.homework.id, "monday": True,
        })
        self.assertFalse(self.pe_class._generate_assignments(self.semester_1))

    def test_report_card(self):
        lesson = self._assignment()
        self._score(lesson, self.anna, 88)
        self._mark(self.section_5, self.anna, comment="Works carefully.")
        self._mark(self.pe_class, self.anna, letter="A")
        self._mark(self.conduct_class, self.anna, comment="Kind to others.")
        wizard = self.env["school.grade.report"].create({
            "year_id": self.year.id, "period_id": self.semester_1.id, "student_ids": self.anna.ids,
        })
        card, = wizard._get_report_cards()
        rows = {row["course"]: row for row in card["rows"]}
        self.assertEqual(list(rows), ["Test Math 5", "Test PE", "Test Conduct"])
        self.assertEqual(rows["Test Math 5"]["grades"], [{"grade": "88", "letter": "B"}])
        self.assertEqual(rows["Test Math 5"]["comment"], "Works carefully.")
        self.assertEqual(rows["Test PE"]["grades"], [{"grade": "", "letter": "A"}])
        self.assertEqual(rows["Test PE"]["year"], {"grade": "", "letter": ""})
        self.assertEqual(rows["Test Conduct"]["grades"], [{"grade": "", "letter": ""}])
        self.assertEqual(rows["Test Conduct"]["comment"], "Kind to others.")
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_school_gradebook.report_card", wizard.ids
        )[0].decode()
        self.assertIn("Kind to others.", html)
        self.assertIn("Works carefully.", html)
        header, lines = wizard._csv_rows()
        self.assertEqual(header[-1], "Comment")
        self.assertEqual(lines[2][-1], "Kind to others.")
        # Letter and comment courses have no class sheet or progress report.
        sheets = wizard.copy({"report_type": "class_sheet", "student_ids": False})._get_class_sheets()
        self.assertEqual([sheet["section"] for sheet in sheets], [self.section_5, self.section_6])

    def test_day_off_removes_unscored_assignments(self):
        self.semester_1.date_end = "2030-09-13"
        self.env["school.assignment.template"].create({
            "course_id": self.math_5.id, "name": "Lesson", "category_id": self.homework.id,
            "monday": True, "tuesday": True,
        })
        created = self.section_5._generate_assignments(self.semester_1)
        self.assertEqual(len(created), 6)
        scored = created.filtered(lambda a: a.date == date(2030, 9, 3))
        self._score(scored, self.anna, 90)
        # Two days become days off; one already has a score and stays.
        self.env["school.calendar.day"].create({
            "year_id": self.year.id, "name": "Storm", "date_start": "2030-09-02", "date_end": "2030-09-03",
        })
        self.assertFalse(self.section_5._generate_assignments(self.semester_1))
        dates = self.section_5.assignment_ids.mapped("date")
        self.assertNotIn(date(2030, 9, 2), dates)
        self.assertIn(date(2030, 9, 3), dates)
        self.assertEqual(len(dates), 5)

    def test_setup_guide_steps(self):
        guide = self.env["school.setup.guide"].create({})
        self.assertEqual(guide.template_count, self.env["school.assignment.template"].search_count([]))
        self._assignment()
        guide.invalidate_recordset()
        self.assertEqual(guide.assignment_count, 1)
        self.assertEqual(guide.action_templates()["res_model"], "school.assignment.template")
        self.assertEqual(guide.action_generate_assignments()["res_model"], "school.assignment.generate")
        self.assertEqual(guide.action_assignments()["res_model"], "school.assignment")
        # The guide's form loads with the gradebook's steps.
        arch = self.env["school.setup.guide"].get_view(view_type="form")["arch"]
        self.assertIn("step_templates", arch)
