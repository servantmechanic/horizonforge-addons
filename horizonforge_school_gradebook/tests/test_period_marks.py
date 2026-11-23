from datetime import date

from odoo.exceptions import AccessError, ValidationError
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestPeriodMarks(GradebookCase):
    """Letter courses in the gradebook, letters per assignment, and report
    card comments."""

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
        # A letter course types letters, unless it says otherwise.
        self.assertEqual(self.pe_class._get_entry_mode(), "letter")
        self.pe.entry_mode = "percent"
        self.assertEqual(self.pe_class._get_entry_mode(), "percent")

    def test_scale_values_when_entered(self):
        letters = self.env.ref("horizonforge_school_gradebook.grading_scale_letters")
        values = {line.letter: line.entry_percent for line in letters.line_ids}
        # The middle of each range; F, the lowest, 5 below the top of its range.
        self.assertEqual(values, {"A": 96.5, "B": 89, "C": 81, "D": 73.5, "F": 65})
        esnu = self.env.ref("horizonforge_school_gradebook.grading_scale_esnu")
        self.assertEqual(esnu._entry_percent(" s "), 85)
        self.assertIsNone(esnu._entry_percent("B"))

    def test_letter_scores(self):
        activity = self._assignment(section=self.pe_class, name="Activity")
        self.assertEqual(activity.entry_mode, "letter")
        score = self._score(activity, self.anna, letter_entered=" b ")
        self.assertEqual(score.letter_entered, "B")
        self.assertEqual(score.percent, 89)
        with self.assertRaises(ValidationError):
            score.letter_entered = "Q"
        # The lower grades' scale has its own letters and values.
        self.level_5.grading_scale_id = self.env.ref("horizonforge_school_gradebook.grading_scale_esnu")
        with self.assertRaises(ValidationError):
            self._score(activity, self.ben, letter_entered="B")
        ben = self._score(activity, self.ben, letter_entered="s")
        self.assertEqual(ben.percent, 85)
        # The school changes what S counts for: the score follows.
        line = ben._get_grading_scale().line_ids.filtered(lambda l: l.letter == "S")
        line.entry_percent = 88
        self.assertEqual(ben.percent, 88)
        # Excused and missing work as usual.
        ben.write({"status": "excused", "letter_entered": False})
        self.assertEqual(ben.percent, 0)

    def test_letter_assignment_in_percent_course(self):
        essay = self._assignment(name="Essay", entry_mode="letter")
        quiz = self._assignment(name="Quiz", date="2030-09-04")
        result = self.env["school.score"].with_user(self.teacher).save_batch([
            {"assignment_id": essay.id, "student_id": self.anna.id, "status": "scored", "value": "a"},
            {"assignment_id": essay.id, "student_id": self.ben.id, "status": "scored", "value": "Z"},
            {"assignment_id": quiz.id, "student_id": self.anna.id, "status": "scored", "value": 81},
        ])
        cells = {(c["assignment_id"], c["student_id"]): c for c in result["saved"]}
        self.assertEqual(cells[essay.id, self.anna.id]["value"], "A")
        self.assertEqual(cells[essay.id, self.anna.id]["percent"], 96.5)
        self.assertEqual([e["student_id"] for e in result["errors"]], self.ben.ids)
        # (96.5 + 81) / 2 = 88.75: rounds to 89, a B.
        grade = result["grades"][0]["grades"][self.anna.id]
        self.assertEqual((grade["grade"], grade["letter"]), ("89", "B"))
        # Scores typed one way can't silently become the other.
        with self.assertRaises(ValidationError):
            essay.entry_mode = "percent"
        with self.assertRaises(ValidationError):
            quiz.entry_mode = "letter"

    def test_letter_courses_in_the_gradebook(self):
        sections = self.env["school.section"].with_user(self.teacher)._gradebook_sections()
        self.assertEqual(sections, self.section_5 | self.pe_class)
        data = self.pe_class.with_user(self.teacher).gradebook_open(self.pe_class.id, self.semester_1.id)
        self.assertTrue(data["letter_only"])
        self.assertEqual(data["entry_mode"], "letter")
        scale_id = data["students"][0]["scale_id"]
        self.assertEqual([line["letter"] for line in data["scales"][scale_id]], ["A", "B", "C", "D", "F"])
        self.assertFalse(self.env["school.section"].gradebook_open(self.section_5.id)["letter_only"])
        # Schedules generate letter assignments; comment-only courses stay out.
        self.semester_1.date_end = "2030-09-06"
        for course in (self.pe, self.conduct):
            self.env["school.assignment.template"].create({
                "course_id": course.id, "name": "Activity", "category_id": self.homework.id, "monday": True,
            })
        created = self.pe_class._generate_assignments(self.semester_1)
        self.assertEqual(created.mapped("entry_mode"), ["letter", "letter"])  # two Mondays
        self.assertFalse(self.conduct_class._generate_assignments(self.semester_1))

    def test_open_creates_rows(self):
        action = self.conduct_class.with_user(self.teacher).action_open_period_marks()
        marks = self.Mark.search([("section_id", "=", self.conduct_class.id)])
        # The year hasn't started: the first period only, a row per student.
        self.assertEqual(marks.mapped("period_id"), self.semester_1)
        self.assertEqual(marks.student_id, self.anna | self.ben)
        self.assertEqual(action["domain"], [("section_id", "in", self.conduct_class.ids)])
        self.conduct_class.with_user(self.teacher).action_open_period_marks()
        self.assertEqual(self.Mark.search_count([("section_id", "=", self.conduct_class.id)]), 2)
        marks[0].with_user(self.teacher).comment = "Great effort"

    def test_menu_opens_own_classes(self):
        """From the menu: rows for the teacher's classes, shown with My Classes
        and the period picked in the side panel, none of it fixed."""
        action = self.Mark.with_user(self.teacher).action_open_marks()
        self.assertFalse(action.get("domain"))
        context = action["context"]
        self.assertEqual(context["search_default_my_classes"], 1)
        self.assertEqual(context["search_default_current_year"], 1)
        self.assertEqual(context["searchpanel_default_period_id"], self.semester_1.id)
        sections = self.Mark.search([]).section_id
        self.assertEqual(sections, self.section_5 | self.pe_class | self.conduct_class)
        # The office starts on every class.
        context = self.Mark.with_user(self.office).action_open_marks()["context"]
        self.assertNotIn("search_default_my_classes", context)

    def test_security_and_lock(self):
        mark = self._mark(self.conduct_class, self.anna, comment="Kind")
        with self.assertRaises(AccessError):
            mark.with_user(self.other_teacher).read(["comment"])
        with self.assertRaises(AccessError):
            mark.with_user(self.office).comment = "Changed"
        self.assertEqual(mark.with_user(self.office).comment, "Kind")
        self.semester_1.locked = True
        with self.assertRaises(ValidationError):
            mark.with_user(self.teacher).comment = "Changed"
        mark.with_user(self.admin).comment = "Changed"

    def test_comment_from_the_grid(self):
        Section = self.env["school.section"].with_user(self.teacher)
        section = Section.browse(self.section_5.id)
        self.assertEqual(section.gradebook_set_comment(self.semester_1.id, self.anna.id, " Neat work "), "Neat work")
        data = Section.gradebook_open(self.section_5.id, self.semester_1.id)
        self.assertEqual(data["comments"], {self.anna.id: "Neat work"})
        self.assertEqual(section.gradebook_set_comment(self.semester_1.id, self.anna.id, ""), "")
        self.assertFalse(Section.gradebook_open(self.section_5.id, self.semester_1.id)["comments"])
        # Nothing typed, nothing created.
        section.gradebook_set_comment(self.semester_1.id, self.ben.id, "")
        self.assertFalse(self.Mark.search([("student_id", "=", self.ben.id), ("section_id", "=", self.section_5.id)]))
        with self.assertRaises(AccessError):
            self.section_5.with_user(self.office).gradebook_set_comment(self.semester_1.id, self.anna.id, "No")

    def test_report_card(self):
        lesson = self._assignment()
        self._score(lesson, self.anna, 88)
        self._mark(self.section_5, self.anna, comment="Works carefully.")
        # PE by letters: A (96.5) and B (89) average 92.75, an A.
        for name, letter in (("Run", "A"), ("Throw", "B")):
            self._score(self._assignment(section=self.pe_class, name=name), self.anna, letter_entered=letter)
        self._mark(self.conduct_class, self.anna, comment="Kind to others.")
        wizard = self.env["school.grade.report"].create({
            "year_id": self.year.id, "period_id": self.semester_1.id, "student_ids": self.anna.ids,
        })
        card, = wizard._get_report_cards()
        rows = {row["course"]: row for row in card["rows"]}
        self.assertEqual(list(rows), ["Test Math 5", "Test PE", "Test Conduct"])
        self.assertEqual(rows["Test Math 5"]["grades"], [{"grade": "88", "letter": "B"}])
        self.assertEqual(rows["Test Math 5"]["comment"], "Works carefully.")
        self.assertEqual(rows["Test PE"]["grades"], [{"grade": "93", "letter": "A"}])
        self.assertEqual(rows["Test Conduct"]["grades"], [{"grade": "", "letter": ""}])
        self.assertEqual(rows["Test Conduct"]["comment"], "Kind to others.")
        # The folded card prints the letter course as letters only.
        page, = wizard._get_card_pages()
        subjects = {subject["course"]: subject for subject in page["subjects"]}
        self.assertEqual(subjects["Test PE"]["cells"][0], "A")
        self.assertEqual(subjects["Test PE"]["average"], "A")
        self.assertEqual(subjects["Test Math 5"]["average"], "88")
        self.assertNotIn("Test Conduct", subjects)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_school_gradebook.report_card", wizard.ids
        )[0].decode()
        self.assertIn("Kind to others.", html)
        self.assertIn("Works carefully.", html)
        header, lines = wizard._csv_rows()
        self.assertEqual(header[-1], "Comment")
        self.assertEqual(lines[2][-1], "Kind to others.")
        # Comment-only courses have no class sheet or progress report.
        sheets = wizard.copy({"report_type": "class_sheet", "student_ids": False})._get_class_sheets()
        self.assertEqual([sheet["section"] for sheet in sheets], [self.section_5, self.section_6, self.pe_class])
        progress = wizard.copy({"report_type": "progress"})._get_progress_reports()
        pe_page = next(page for page in progress if page["section"] == self.pe_class)
        self.assertEqual([row["score"] for row in pe_page["rows"]], ["A", "B"])

    def test_not_in_the_gradebook(self):
        self.assertNotIn(self.conduct_class, self.env["school.section"].with_user(self.teacher)._gradebook_sections())

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
        # Monday's unscored lesson leaves the day off for the next school
        # day; Tuesday's, already scored, stays where it is.
        moved = self.section_5._generate_assignments(self.semester_1)
        self.assertEqual(moved.mapped("date"), [date(2030, 9, 4)])
        dates = self.section_5.assignment_ids.mapped("date")
        self.assertNotIn(date(2030, 9, 2), dates)
        self.assertIn(date(2030, 9, 3), dates)
        self.assertEqual(len(dates), 6)
        self.assertFalse(self.section_5._generate_assignments(self.semester_1))

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
