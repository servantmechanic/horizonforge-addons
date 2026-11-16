from odoo import api, models
from odoo.tools import float_round


class SchoolGradeEngine(models.AbstractModel):
    """Every grade the school addons show comes from here: the gradebook
    grid, the reports and the exports, so they always agree.

    A grade is a dict::

        {
            "percent": 84.5,       # weighted average, not rounded (None without scores)
            "grade": 85.0,         # rounded as the school rounds period grades
            "letter": "B",         # from the grading scale, on the rounded grade
            "categories": {category_id: average},   # only categories with scores
        }
    """

    _name = "school.grade.engine"
    _description = "Grade Calculation"

    # ------------------------------------------------------------------
    # Pure calculation: no database access
    # ------------------------------------------------------------------

    @api.model
    def _round(self, value, digits):
        """Round half up: 92.5 becomes 93."""
        return float_round(value, precision_digits=digits, rounding_method="HALF-UP")

    @api.model
    def _category_average(self, entries, method="average", missing_as_zero=True):
        """Average of one category.

        :param entries: list of ``(status, percent, max_points)``
        :param method: "average" (mean of the percents, every assignment
            counts equally) or "points" (points earned over points possible)
        :return: the average, or None when nothing counts
        """
        counted = []
        for status, percent, max_points in entries:
            if status == "excused":
                continue
            if status == "missing":
                if not missing_as_zero:
                    continue
                percent = 0.0
            counted.append((percent, max_points))
        if not counted:
            return None
        if method == "points":
            possible = sum(max_points for _percent, max_points in counted)
            if not possible:
                return None
            earned = sum(percent / 100.0 * max_points for percent, max_points in counted)
            return earned / possible * 100.0
        return sum(percent for percent, _max_points in counted) / len(counted)

    @api.model
    def _weighted_average(self, averages, weights=None):
        """Weighted average of the category averages. The weight of a
        category without scores is re-spread over the others.

        :param averages: ``{category_id: average or None}``
        :param weights: ``{category_id: weight}``; None weighs them equally
        """
        total = weight_sum = 0.0
        for category_id, average in averages.items():
            if average is None:
                continue
            weight = 1.0 if weights is None else weights.get(category_id, 0.0)
            total += weight * average
            weight_sum += weight
        return total / weight_sum if weight_sum else None

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    @api.model
    def _settings(self):
        company = self.env.company
        return {
            "missing_as_zero": company.school_missing_work == "zero",
            "grade_decimals": company.school_grade_decimals,
            "display_decimals": company.school_display_decimals,
            "year_grade": company.school_year_grade,
        }

    @api.model
    def _weights(self, section):
        """``(method, {category_id: weight})`` for a class; the weights are
        None without a weight scheme (categories then count equally)."""
        scheme = section._get_weight_scheme()
        if not scheme:
            return "average", None
        return scheme.method, {line.category_id.id: line.weight for line in scheme.line_ids}

    @api.model
    def _grade(self, percent, scale, settings):
        """Round a raw percent and look up its letter."""
        if percent is None:
            return {"percent": None, "grade": None, "letter": ""}
        grade = self._round(percent, settings["grade_decimals"])
        return {
            "percent": percent,
            "grade": grade,
            "letter": scale._get_letter(grade) if scale else "",
        }

    @api.model
    def _format(self, value, digits=None):
        """A grade or average as text, empty when there is none."""
        if value is None or value is False:
            return ""
        if digits is None:
            digits = self.env.company.school_grade_decimals
        return f"{self._round(value, digits):.{digits}f}"

    # ------------------------------------------------------------------
    # Grades of a class
    # ------------------------------------------------------------------

    @api.model
    def _section_grades(self, section, period=None, students=None):
        """Grades of the students of one class for a grading period, for
        several periods taken together, or over the whole year without
        ``period``.

        :return: ``{student_id: grade}`` for every student asked for (or
            every student with a score)
        """
        settings = self._settings()
        method, weights = self._weights(section)
        domain = [("section_id", "=", section.id)]
        if period:
            domain.append(("period_id", "in", period.ids))
        if students is not None:
            domain.append(("student_id", "in", students.ids))
        entries = {}  # student id -> category id -> [(status, percent, max_points)]
        for score in self.env["school.score"].search(domain):
            assignment = score.assignment_id
            entries.setdefault(score.student_id.id, {}).setdefault(
                assignment.category_id.id, []
            ).append((score.status, score.percent, assignment.max_points))

        Student = self.env["school.student"].with_context(active_test=False)
        student_ids = students.ids if students is not None else list(entries)
        grades = {}
        for student in Student.browse(student_ids):
            averages = {
                category_id: self._category_average(
                    category_entries, method, settings["missing_as_zero"]
                )
                for category_id, category_entries in entries.get(student.id, {}).items()
            }
            averages = {c: average for c, average in averages.items() if average is not None}
            grade = self._grade(
                self._weighted_average(averages, weights),
                section._get_grading_scale(student),
                settings,
            )
            grade["categories"] = averages
            grades[student.id] = grade
        return grades

    @api.model
    def _section_year_grades(self, section, students=None, periods=None):
        """Year grades of a class: the average of the period grades, or one
        grade over all the year's scores, by the school's setting.

        :param periods: only count these periods (year to date)
        """
        settings = self._settings()
        if periods is None:
            periods = section.year_id.period_ids
        if settings["year_grade"] == "cumulative":
            return self._section_grades(section, periods, students)
        by_period = [self._section_grades(section, period, students) for period in periods]
        Student = self.env["school.student"].with_context(active_test=False)
        student_ids = students.ids if students is not None else list(
            {student_id for grades in by_period for student_id in grades}
        )
        result = {}
        for student in Student.browse(student_ids):
            period_grades = [
                grades[student.id]["grade"]
                for grades in by_period
                if grades.get(student.id) and grades[student.id]["grade"] is not None
            ]
            percent = sum(period_grades) / len(period_grades) if period_grades else None
            grade = self._grade(percent, section._get_grading_scale(student), settings)
            grade["categories"] = {}
            result[student.id] = grade
        return result

    @api.model
    def _class_average(self, grades):
        """Average of the students' (rounded) grades, None without any."""
        values = [grade["grade"] for grade in grades.values() if grade["grade"] is not None]
        return sum(values) / len(values) if values else None
