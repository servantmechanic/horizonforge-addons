from odoo.tests import tagged

from ..models.school_chart import performance_svg, value_floor
from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestClassPerformance(GradebookCase):
    """The student vs class average chart: the engine's averages, the SVG,
    and the Class Performance report."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.write({
            "school_missing_work": "zero",
            "external_report_layout_id": cls.env.ref("web.external_layout_standard").id,
        })
        cls.first = cls._assignment(name="Lesson 1", date="2030-09-03")
        cls.second = cls._assignment(name="Lesson 2", date="2030-09-04")
        cls.third = cls._assignment(name="Lesson 3", date="2030-09-05")
        # Anna 90, 80, -; Ben 70, missing, excused. Carl (grade 6) in Math 6.
        cls._score(cls.first, cls.anna, 90)
        cls._score(cls.second, cls.anna, 80)
        cls._score(cls.first, cls.ben, 70)
        cls._score(cls.second, cls.ben, status="missing")
        cls._score(cls.third, cls.ben, status="excused")
        other = cls._assignment(section=cls.section_6, name="Other", date="2030-09-03")
        cls._score(other, cls.carl, 95)

    def _wizard(self, **vals):
        return self.env["school.grade.report"].create({
            "report_type": "performance", "year_id": self.year.id, "period_id": self.semester_1.id, **vals,
        })

    def test_assignment_averages(self):
        Engine = self.env["school.grade.engine"]
        averages = Engine._assignment_averages(self.first | self.second | self.third)
        # Missing counts 0; excused doesn't count; no scores: None.
        self.assertEqual(averages, {self.first.id: 80, self.second.id: 40, self.third.id: None})
        self.env.company.school_missing_work = "skip"
        self.assertEqual(Engine._assignment_averages(self.second)[self.second.id], 80)
        self.assertIsNone(Engine._score_point("missing", 0, missing_as_zero=False))
        self.assertEqual(Engine._score_point("missing", 0), 0)
        self.assertIsNone(Engine._score_point("excused", 0))

    def test_svg(self):
        self.assertEqual(value_floor([95, 88, None]), 60)
        self.assertEqual(value_floor([42, 90]), 40)
        svg = str(performance_svg([80, 40, None], [90, None, 70]))
        self.assertTrue(svg.startswith("<svg"))
        # The class average is one run; the student's gap splits theirs,
        # so they get dots and no line.
        self.assertEqual(svg.count("<polygon"), 1)
        self.assertEqual(svg.count('stroke="#2a78d6"'), 0)
        self.assertEqual(svg.count("<circle"), 2)
        # The axis starts low enough for the 40.
        self.assertIn(">40</text>", svg)

    def test_report(self):
        page_5, page_6 = self._wizard()._get_performance()
        self.assertEqual(page_5["section"], self.section_5)
        # Lesson 3 has nothing counted yet (one excused score): left off the end.
        self.assertEqual(page_5["assignments"], self.first | self.second)
        self.assertEqual(page_5["averages"], [80, 40])
        rows = {row["student"]: row for row in page_5["rows"]}
        self.assertEqual(rows[self.anna]["points"], [90, 80])
        self.assertEqual(rows[self.ben]["points"], [70, 0])
        self.assertEqual((rows[self.anna]["grade"], rows[self.anna]["letter"]), ("85", "B"))
        self.assertIn("<svg", str(rows[self.anna]["chart"]))
        self.assertEqual(page_6["section"], self.section_6)

    def test_choose_grade_levels_and_subjects(self):
        pages = self._wizard(grade_level_ids=self.level_6.ids)._get_performance()
        self.assertEqual([page["section"] for page in pages], [self.section_6])
        pages = self._wizard(course_ids=self.math_5.ids)._get_performance()
        self.assertEqual([page["section"] for page in pages], [self.section_5])
        # One student printed: the class average still counts everyone.
        page, = self._wizard(course_ids=self.math_5.ids, student_ids=self.anna.ids)._get_performance()
        self.assertEqual([row["student"] for row in page["rows"]], [self.anna])
        self.assertEqual(page["averages"], [80, 40])

    def test_teacher_sees_own_classes(self):
        Wizard = self.env["school.grade.report"].with_user(self.teacher)
        wizard = Wizard.create({"report_type": "performance", "year_id": self.year.id, "period_id": self.semester_1.id})
        self.assertEqual([page["section"] for page in wizard._get_performance()], [self.section_5])

    def test_pdf_and_csv(self):
        wizard = self._wizard(course_ids=self.math_5.ids)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_school_gradebook.report_performance", wizard.ids
        )[0].decode()
        self.assertIn("Class Performance", html)
        self.assertEqual(html.count("<svg"), 2)
        header, rows = wizard._csv_rows()
        self.assertEqual(header[-2:], ["Percent", "Class Average"])
        self.assertEqual(len(rows), 4)  # 2 students x 2 assignments scored so far
        ben = [row for row in rows if row[3] == "Ben"]
        self.assertEqual([(row[-2], row[-1]) for row in ben], [("70.0", "80.0"), ("0.0", "40.0")])
        self.assertEqual(wizard.action_print()["report_name"], "horizonforge_school_gradebook.report_performance")
