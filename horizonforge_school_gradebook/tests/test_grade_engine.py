from odoo import Command
from odoo.tests import tagged

from .common import GradebookCase


@tagged("post_install", "-at_install")
class TestGradeEngine(GradebookCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Engine = cls.env["school.grade.engine"]
        cls.company = cls.env.company
        cls.company.write({
            "school_missing_work": "zero",
            "school_grade_decimals": 0,
            "school_display_decimals": 1,
            "school_year_grade": "average",
        })
        cls.scheme = cls.company.school_weight_scheme_id  # HW 50, Test 50, average
        cls.section_5.weight_scheme_id = False
        cls.math_5.weight_scheme_id = False

    def _scores(self, student, homework=(), tests=(), date="2030-09-03", **vals):
        """Percent scores; "x" is excused, "m" missing, None left empty."""
        for category, values in ((self.homework, homework), (self.test, tests)):
            for value in values:
                assignment = self._assignment(category_id=category.id, date=date, **vals)
                if value is None:
                    continue
                if value in ("x", "m"):
                    self._score(assignment, student, status="excused" if value == "x" else "missing")
                else:
                    self._score(assignment, student, value)

    def _grade(self, student=None, period=None):
        student = student or self.anna
        return self.Engine._section_grades(self.section_5, period or self.semester_1, student)[student.id]

    # Pure calculation

    def test_round_half_up(self):
        self.assertEqual(self.Engine._round(92.5, 0), 93)
        self.assertEqual(self.Engine._round(92.49, 0), 92)
        self.assertEqual(self.Engine._round(84.5, 0), 85)
        self.assertEqual(self.Engine._round(84.45, 1), 84.5)
        self.assertEqual(self.Engine._round(69.995, 2), 70.0)

    def test_category_average_methods(self):
        entries = [("scored", 100.0, 10), ("scored", 50.0, 90)]
        self.assertEqual(self.Engine._category_average(entries, "average"), 75)
        # Total points: 10 + 45 of 100 possible. The big assignment counts more.
        self.assertAlmostEqual(self.Engine._category_average(entries, "points"), 55)

    def test_category_average_statuses(self):
        entries = [("scored", 80.0, 100), ("excused", 0.0, 100), ("missing", 0.0, 100)]
        self.assertEqual(self.Engine._category_average(entries, "average", True), 40)
        self.assertEqual(self.Engine._category_average(entries, "average", False), 80)
        self.assertEqual(self.Engine._category_average(entries, "points", True), 40)
        self.assertEqual(self.Engine._category_average(entries, "points", False), 80)
        self.assertIsNone(self.Engine._category_average([("excused", 0.0, 100)], "average"))
        self.assertIsNone(self.Engine._category_average([("missing", 0.0, 100)], "average", False))
        self.assertEqual(self.Engine._category_average([("missing", 0.0, 100)], "average", True), 0)
        self.assertIsNone(self.Engine._category_average([], "points"))

    def test_weighted_average(self):
        weights = {1: 50.0, 2: 50.0}
        self.assertEqual(self.Engine._weighted_average({1: 90.0, 2: 80.0}, weights), 85)
        self.assertEqual(self.Engine._weighted_average({1: 90.0, 2: 80.0}, {1: 30.0, 2: 70.0}), 83)
        # An empty category: its weight is re-spread over the others.
        self.assertEqual(self.Engine._weighted_average({1: 90.0, 2: None}, weights), 90)
        self.assertEqual(self.Engine._weighted_average({1: 90.0}, weights), 90)
        # A category outside the scheme doesn't count.
        self.assertEqual(self.Engine._weighted_average({1: 90.0, 3: 10.0}, weights), 90)
        self.assertIsNone(self.Engine._weighted_average({3: 10.0}, weights))
        self.assertIsNone(self.Engine._weighted_average({}, weights))
        # No scheme: the categories count equally.
        self.assertEqual(self.Engine._weighted_average({1: 90.0, 3: 70.0}), 80)

    # Period grades

    def test_worked_example(self):
        """The spec's example: HW 90, 80, 100 average 90; tests 84, 76
        average 80; (50 x 90 + 50 x 80) / 100 = 85, a B."""
        self._scores(self.anna, homework=(90, 80, 100), tests=(84, 76))
        grade = self._grade()
        self.assertEqual(grade["categories"], {self.homework.id: 90.0, self.test.id: 80.0})
        self.assertEqual(grade["percent"], 85)
        self.assertEqual(grade["grade"], 85)
        self.assertEqual(grade["letter"], "B")

    def test_no_scores(self):
        self._scores(self.anna, homework=(None,))
        grade = self._grade()
        self.assertIsNone(grade["grade"])
        self.assertEqual(grade["letter"], "")
        self.assertEqual(grade["categories"], {})
        self.assertEqual(self.Engine._format(grade["grade"]), "")

    def test_empty_category_respread(self):
        self._scores(self.anna, homework=(90, 70))
        self.assertEqual(self._grade()["grade"], 80)
        self._scores(self.anna, tests=("x",))  # an excused test doesn't open the category
        self.assertEqual(self._grade()["grade"], 80)
        self._scores(self.anna, tests=(60,))
        self.assertEqual(self._grade()["grade"], 70)

    def test_excused_and_blank_left_out(self):
        self._scores(self.anna, homework=(90, "x", None, 70), tests=(80,))
        grade = self._grade()
        self.assertEqual(grade["categories"][self.homework.id], 80)
        self.assertEqual(grade["grade"], 80)

    def test_missing_work_setting(self):
        self._scores(self.anna, homework=(90, "m"), tests=(80,))
        self.assertEqual(self._grade()["grade"], 63)  # (45 + 80) / 2 = 62.5
        self.company.school_missing_work = "skip"
        self.assertEqual(self._grade()["grade"], 85)

    def test_entry_modes_mix(self):
        self._scores(self.anna, homework=(22,), entry_mode="points", max_points=25)   # 88%
        self._scores(self.anna, homework=(3,), entry_mode="wrong", max_points=20)     # 85%
        self._scores(self.anna, homework=(91,))                                       # 91%
        self.assertAlmostEqual(self._grade()["categories"][self.homework.id], 88.0)

    def test_total_points_method(self):
        scheme = self.scheme.copy({"name": "Points", "method": "points"})
        self.section_5.weight_scheme_id = scheme
        self._scores(self.anna, homework=(10,), entry_mode="points", max_points=10)   # 10 of 10
        self._scores(self.anna, homework=(45,), entry_mode="points", max_points=90)   # 45 of 90
        self._scores(self.anna, homework=(50,), max_points=100)                       # 50% of 100
        # 105 of 200 points; averaging the percents would give 66.7.
        self.assertAlmostEqual(self._grade()["categories"][self.homework.id], 52.5)
        self.assertEqual(self._grade()["grade"], 53)

    def test_rounding_at_letter_boundaries(self):
        # (percent, grade, letter) with whole-number rounding, half up.
        for homework, test, grade, letter in [
            (93, 92, 93, "A"),    # 92.5 rounds up to an A
            (92, 92.9, 92, "B"),  # 92.45 stays a B
            (85, 84, 85, "B"),    # 84.5
            (84, 84.9, 84, "C"),  # 84.45
            (70, 69, 70, "D"),    # 69.5
            (69, 69.9, 69, "F"),  # 69.45
        ]:
            self.env["school.assignment"].search([("section_id", "=", self.section_5.id)]).unlink()
            self._scores(self.anna, homework=(homework,), tests=(test,))
            result = self._grade()
            self.assertEqual((result["grade"], result["letter"]), (grade, letter), (homework, test))

    def test_grade_decimals_setting(self):
        self._scores(self.anna, homework=(93,), tests=(92,))
        self.company.school_grade_decimals = 1
        grade = self._grade()
        self.assertEqual(grade["grade"], 92.5)
        self.assertEqual(grade["letter"], "B")  # 92.5 is under 93 when not rounded up
        self.assertEqual(self.Engine._format(grade["grade"]), "92.5")

    def test_weight_scheme_by_course_and_class(self):
        self._scores(self.anna, homework=(100,), tests=(60,))
        self.assertEqual(self._grade()["grade"], 80)
        self.math_5.weight_scheme_id = self.scheme.copy({
            "name": "Tests heavy",
            "line_ids": [
                Command.clear(),
                Command.create({"category_id": self.homework.id, "weight": 25}),
                Command.create({"category_id": self.test.id, "weight": 75}),
            ],
        })
        self.assertEqual(self._grade()["grade"], 70)
        self.section_5.weight_scheme_id = self.scheme
        self.assertEqual(self._grade()["grade"], 80)

    def test_scale_by_grade_level(self):
        self._scores(self.anna, homework=(88,))
        self.level_5.grading_scale_id = self.env["school.grading.scale"].create({
            "name": "Lower grades",
            "line_ids": [
                Command.create({"letter": "S", "min_percent": 70}),
                Command.create({"letter": "N", "min_percent": 0}),
            ],
        })
        self.assertEqual(self._grade()["letter"], "S")

    def test_changes_recalculate_without_retyping(self):
        self._scores(self.anna, homework=(20,), entry_mode="points", max_points=25)
        self.assertEqual(self._grade()["grade"], 80)
        self.section_5.assignment_ids.max_points = 40
        self.assertEqual(self._grade()["grade"], 50)

    def test_only_the_period_and_the_class(self):
        self._scores(self.anna, homework=(90,))
        self._scores(self.anna, homework=(50,), date="2031-02-03")   # semester 2
        other = self._assignment(section=self.section_6, category_id=self.homework.id)
        self._score(other, self.carl, 10)
        self.assertEqual(self._grade()["grade"], 90)
        self.assertEqual(self._grade(period=self.semester_2)["grade"], 50)
        grades = self.Engine._section_grades(self.section_5, self.semester_1)
        self.assertEqual(set(grades), {self.anna.id})

    # Year grades and class average

    def test_year_grade_average_of_periods(self):
        self._scores(self.anna, homework=(90, 91))            # semester 1: 90.5 -> 91
        self._scores(self.anna, homework=(80,), date="2031-02-03")
        year = self.Engine._section_year_grades(self.section_5, self.anna)[self.anna.id]
        self.assertEqual(year["grade"], 86)  # (91 + 80) / 2 = 85.5
        self.assertEqual(year["letter"], "B")
        # Year to date: only the first period.
        so_far = self.Engine._section_year_grades(self.section_5, self.anna, self.semester_1)
        self.assertEqual(so_far[self.anna.id]["grade"], 91)

    def test_year_grade_cumulative(self):
        self.company.school_year_grade = "cumulative"
        self._scores(self.anna, homework=(90, 91))
        self._scores(self.anna, homework=(80,), date="2031-02-03")
        year = self.Engine._section_year_grades(self.section_5, self.anna)[self.anna.id]
        self.assertEqual(year["grade"], 87)  # (90 + 91 + 80) / 3
        so_far = self.Engine._section_year_grades(self.section_5, self.anna, self.semester_1)
        self.assertEqual(so_far[self.anna.id]["grade"], 91)

    def test_year_grade_skips_empty_periods(self):
        self._scores(self.anna, homework=(77,))
        year = self.Engine._section_year_grades(self.section_5, self.anna)[self.anna.id]
        self.assertEqual((year["grade"], year["letter"]), (77, "C"))
        empty = self.Engine._section_year_grades(self.section_5, self.ben)[self.ben.id]
        self.assertIsNone(empty["grade"])

    def test_class_average(self):
        self._scores(self.anna, homework=(90,))
        self._scores(self.ben, homework=(81,))
        students = self.anna | self.ben
        grades = self.Engine._section_grades(self.section_5, self.semester_1, students)
        self.assertEqual(self.Engine._class_average(grades), 85.5)
        self.assertEqual(self.Engine._format(self.Engine._class_average(grades), 1), "85.5")
        self.assertIsNone(self.Engine._class_average({}))

    # The grid

    def test_grid_grades(self):
        self._scores(self.anna, homework=(90, 80, 100), tests=(84, 76))
        data = self.env["school.section"].with_user(self.teacher).gradebook_open(
            self.section_5.id, self.semester_1.id
        )
        self.assertEqual(data["grades"][self.anna.id], {
            "grade": "85", "letter": "B",
            "categories": {self.homework.id: "90.0", self.test.id: "80.0"},
        })
        self.assertEqual(data["grades"][self.ben.id], {"grade": "", "letter": "", "categories": {}})
        self.assertEqual(data["class_average"], "85.0")
        self.assertEqual(data["weights"], {self.homework.id: 50.0, self.test.id: 50.0})

    def test_save_batch_returns_grades(self):
        assignment = self._assignment(category_id=self.homework.id)
        result = self.env["school.score"].with_user(self.teacher).save_batch([{
            "assignment_id": assignment.id, "student_id": self.ben.id,
            "status": "scored", "value": 92.5, "comment": "",
        }])
        grades = result["grades"][0]
        self.assertEqual((grades["section_id"], grades["period_id"]), (self.section_5.id, self.semester_1.id))
        self.assertEqual(grades["grades"][self.ben.id]["grade"], "93")
        self.assertEqual(grades["grades"][self.ben.id]["letter"], "A")
        self.assertEqual(grades["class_average"], "93.0")
