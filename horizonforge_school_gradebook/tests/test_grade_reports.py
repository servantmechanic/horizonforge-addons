import base64

from odoo.exceptions import AccessError, UserError
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestGradeReports(GradebookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({
            "school_missing_work": "zero", "school_grade_decimals": 0,
            "school_display_decimals": 1, "school_year_grade": "average",
            "school_principal_name": "Dr. Example",
            # Without a layout, printing first opens Odoo's layout chooser.
            "external_report_layout_id": cls.env.ref("web.external_layout_standard").id,
        })
        cls.anna.homeroom_id = cls.env["school.homeroom"].create({"name": "Report Room"})
        # Anna: HW 90, Test 80 in semester 1 (85 B); HW 70 in semester 2. Ben: one missing.
        cls.lesson = cls._assignment(name="Lesson 1", date="2030-09-03")
        cls.exam = cls._assignment(name="Exam", date="2030-09-10", category_id=cls.test.id,
                                   entry_mode="points", max_points=50)
        cls.later = cls._assignment(name="Lesson 30", date="2031-02-03")
        cls._score(cls.lesson, cls.anna, 90, comment="Neat work")
        cls._score(cls.exam, cls.anna, 40)
        cls._score(cls.later, cls.anna, 70)
        cls._score(cls.lesson, cls.ben, status="missing")
        other = cls._assignment(section=cls.section_6, name="Other", date="2030-09-03")
        cls._score(other, cls.carl, 95)

    def _wizard(self, user=None, **vals):
        Wizard = self.env["school.grade.report"].with_user(user or self.env.user)
        return Wizard.create({"year_id": self.year.id, "period_id": self.semester_1.id, **vals})

    def _html(self, wizard, report):
        html, _type = self.env["ir.actions.report"]._render_qweb_html(
            f"horizonforge_school_gradebook.{report}", wizard.ids
        )
        return html.decode()

    def _csv(self, wizard):
        action = wizard.action_export_csv()
        attachment = self.env["ir.attachment"].browse(int(action["url"].split("/")[3].split("?")[0]))
        lines = base64.b64decode(attachment.datas).decode("utf-8-sig").splitlines()
        return [line.split(",") for line in lines]

    def test_report_card(self):
        wizard = self._wizard(period_id=self.semester_2.id, student_ids=self.anna.ids)
        card, = wizard._get_report_cards()
        self.assertEqual(card["student"], self.anna)
        self.assertEqual(card["periods"], self.semester_1 | self.semester_2)
        row, = card["rows"]
        self.assertEqual(row["course"], "Test Math 5")
        self.assertEqual(row["grades"], [{"grade": "85", "letter": "B"}, {"grade": "70", "letter": "D"}])
        self.assertEqual(row["year"], {"grade": "78", "letter": "C"})  # (85 + 70) / 2 = 77.5
        if "school.attendance" not in self.env:
            self.assertEqual(card["attendance"], [])

        html = self._html(wizard, "report_card")
        for text in ("Report Card", "Anna", "Test Math 5", "Test 2030-31", "CONDUCT GRADES",
                     "Works carefully", "To the Parents:", "The School Board and Teachers"):
            self.assertIn(text, html)
        csv_rows = self._csv(wizard)
        self.assertEqual(csv_rows[0][-5:], ["Semester 2", "Semester 2 Letter", "Year", "Year Letter", "Comment"])
        self.assertEqual(csv_rows[1][1:5], ["Example", "Anna", "Test Grade 5", "Test Math 5"])
        self.assertEqual(csv_rows[1][-7:], ["85", "B", "70", "D", "78", "C", ""])

    def test_report_card_first_period_only(self):
        card, = self._wizard(student_ids=self.anna.ids)._get_report_cards()
        self.assertEqual(card["periods"], self.semester_1)
        self.assertEqual(card["rows"][0]["year"], {"grade": "85", "letter": "B"})

    def test_report_card_batch_by_group(self):
        cards = self._wizard(grade_level_id=self.level_5.id)._get_report_cards()
        self.assertEqual([card["student"] for card in cards], [self.anna, self.ben])
        cards = self._wizard(homeroom_id=self.anna.homeroom_id.id)._get_report_cards()
        self.assertEqual([card["student"] for card in cards], [self.anna])
        everyone = self._wizard()._get_report_cards()
        self.assertEqual({card["student"] for card in everyone} >= {self.anna, self.ben, self.carl}, True)
        # One page per student in the PDF source.
        html = self._html(self._wizard(grade_level_id=self.level_5.id), "report_card")
        self.assertEqual(html.count('<div class="o_title">Report Card</div>'), 2)

    def test_card_pages(self):
        """The folded card lays the grades over every period of the year,
        the later ones blank, with the scale's key."""
        line = self.env.company.school_grading_scale_id.line_ids.filtered(lambda l: l.letter == "A")
        line.description = "Excellent Work"
        page, = self._wizard(student_ids=self.anna.ids)._get_card_pages()
        self.assertEqual(page["periods"], self.year.period_ids)
        subject, = page["subjects"]
        self.assertEqual(subject, {"course": "Test Math 5", "cells": ["85", ""], "average": "85"})
        key = page["keys"][0]
        self.assertEqual(key[0], {"letter": "A", "range": "93-100", "description": "Excellent Work"})
        self.assertEqual(key[1]["range"], "85-92")
        self.assertEqual(key[-1]["range"], "69 and below")
        if "school.attendance" not in self.env:
            self.assertEqual(page["absences"], ["", ""])

    def test_card_comment_course_and_comments(self):
        """A comment-only course has no grade row; its comment prints with
        the others on the back of the card."""
        conduct_course = self.env["school.course"].create({
            "name": "Test Conduct 5", "code": "TCO5", "grading_type": "comment",
            "grade_level_ids": [(6, 0, self.level_5.ids)],
        })
        conduct = self.env["school.section"].create({
            "course_id": conduct_course.id, "year_id": self.year.id, "teacher_id": self.teacher.id,
        })
        conduct.action_enroll_grade_levels()
        self.env["school.period.mark"].create({
            "section_id": conduct.id, "student_id": self.anna.id, "period_id": self.semester_1.id,
            "comment": "A cheerful helper.",
        })
        page, = self._wizard(student_ids=self.anna.ids)._get_card_pages()
        self.assertEqual([s["course"] for s in page["subjects"]], ["Test Math 5"])
        self.assertIn({"course": "Test Conduct 5", "comment": "A cheerful helper."}, page["comments"])
        self.assertIn("A cheerful helper.", self._html(self._wizard(student_ids=self.anna.ids), "report_card"))

    def test_conduct_lines(self):
        company = self.env.company
        company.school_conduct_traits = "Work Habits\n- Enjoys study\n\n* Uses time well\n"
        self.assertEqual(company._school_conduct_lines(),
                         [(True, "Work Habits"), (False, "Enjoys study"), (False, "Uses time well")])
        company.school_conduct_traits = False
        self.assertEqual(company._school_conduct_lines(), [])
        html = self._html(self._wizard(student_ids=self.anna.ids), "report_card")
        self.assertNotIn("CONDUCT GRADES", html)

    def test_reference_sheet(self):
        wizard = self._wizard(report_type="reference", period_id=self.semester_2.id)
        sheets = wizard._get_reference_sheets()
        room = next(sheet for sheet in sheets if sheet["homeroom"] == self.anna.homeroom_id)
        table, = room["tables"]
        self.assertEqual(table["grade_level"], self.level_5)
        self.assertEqual(table["courses"], ["Test Math 5"])
        row, = table["rows"]
        self.assertEqual(row["student"], self.anna)
        self.assertEqual(row["cells"], [{"grade": "70", "average": "78"}])
        # Students without a homeroom come last.
        self.assertFalse(sheets[-1]["homeroom"])
        html = self._html(wizard, "report_card_reference")
        self.assertIn("Report Card Reference", html)
        self.assertIn("Report Room", html)
        self.assertEqual(wizard.action_print()["report_name"],
                         "horizonforge_school_gradebook.report_card_reference")
        self.assertEqual(self._csv(wizard)[1][1:5], ["Example", "Anna", "Test Grade 5", "Test Math 5"])

    def test_class_sheet(self):
        wizard = self._wizard(report_type="class_sheet", section_ids=self.section_5.ids)
        sheet, = wizard._get_class_sheets()
        self.assertEqual(sheet["categories"], self.homework | self.test)
        self.assertEqual(sheet["weights"], {self.homework.id: "50%", self.test.id: "50%"})
        anna, ben = sheet["rows"]
        self.assertEqual((anna["categories"], anna["grade"], anna["letter"]), (["90.0", "80.0"], "85", "B"))
        self.assertEqual((ben["categories"], ben["grade"], ben["letter"]), (["0.0", ""], "0", "F"))
        self.assertEqual(sheet["average"], "42.5")
        html = self._html(wizard, "report_class_sheet")
        self.assertIn("Class average", html)
        self.assertIn("Example, Ben", html)
        csv_rows = self._csv(wizard)
        self.assertEqual(csv_rows[0][-4:], ["Lesson/Homework", "Test", "Grade", "Letter"])
        self.assertEqual(csv_rows[1][-4:], ["90.0", "80.0", "85", "B"])

    def test_progress_report(self):
        wizard = self._wizard(report_type="progress", student_ids=self.anna.ids)
        page, = wizard._get_progress_reports()
        self.assertEqual(page["section"], self.section_5)
        self.assertEqual(
            [(r["name"], r["category"], r["score"], r["percent"], r["comment"]) for r in page["rows"]],
            [("Lesson 1", "HW", "90%", "90.0", "Neat work"), ("Exam", "T", "40/50", "80.0", "")],
        )
        self.assertEqual(page["categories"], [
            {"name": "Lesson/Homework", "average": "90.0"}, {"name": "Test", "average": "80.0"},
        ])
        self.assertEqual((page["grade"], page["letter"]), ("85", "B"))
        html = self._html(wizard, "report_progress")
        for text in ("Progress Report", "Neat work", "40/50", "Period grade"):
            self.assertIn(text, html)
        self.assertEqual(self._csv(wizard)[2][5:9], ["Exam", "T", "40/50", "80.0"])

    def test_progress_report_statuses(self):
        page, = self._wizard(report_type="progress", student_ids=self.ben.ids)._get_progress_reports()
        self.assertEqual([r["score"] for r in page["rows"]], ["M", ""])
        self.assertEqual([r["percent"] for r in page["rows"]], ["", ""])

    def test_missing_work(self):
        wizard = self._wizard(report_type="missing")
        group, = wizard._get_missing_work()
        self.assertEqual(group["section"], self.section_5)
        self.assertEqual(group["count"], 1)
        self.assertEqual(group["rows"], [{"student": self.ben, "assignments": [self.lesson]}])
        html = self._html(wizard, "report_missing")
        self.assertIn("Example, Ben", html)
        self.assertIn("Lesson 1", html)
        self.assertEqual(self._csv(wizard)[1][2:], ["Example", "Ben", "2030-09-03", "Lesson 1"])
        # Whole year, and nothing missing in semester 2.
        self.assertEqual(len(self._wizard(report_type="missing", period_id=False)._get_missing_work()), 1)
        with self.assertRaises(UserError):
            self._wizard(report_type="missing", period_id=self.semester_2.id).action_print()

    def test_print_action(self):
        action = self._wizard(student_ids=self.anna.ids).action_print()
        self.assertEqual(action["report_name"], "horizonforge_school_gradebook.report_card")
        # Teachers can't read report actions themselves.
        action = self._wizard(user=self.teacher).with_user(self.teacher).action_print()
        self.assertEqual(action["report_name"], "horizonforge_school_gradebook.report_card")
        with self.assertRaises(UserError):
            self._wizard(period_id=False).action_print()

    def test_teacher_reports_own_classes_only(self):
        wizard = self._wizard(user=self.teacher)
        self.assertEqual(wizard._get_sections(), self.section_5)
        self.assertEqual({card["student"] for card in wizard._get_report_cards()}, {self.anna, self.ben})
        self.assertEqual(len(wizard.with_user(self.teacher)._csv_rows()[1]), 2)
        with self.assertRaises(AccessError):
            self._wizard(user=self.teacher, section_ids=self.section_6.ids)._get_report_cards()
        office = self._wizard(user=self.office)
        self.assertEqual(
            {card["student"] for card in office._get_report_cards()} >= {self.anna, self.ben, self.carl}, True
        )

    def test_default_period(self):
        wizard = self.env["school.grade.report"].create({"year_id": self.year.id})
        self.assertEqual(wizard.period_id, self.semester_1)  # the year hasn't started
