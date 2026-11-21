import base64
import csv
import io

from odoo import _, api, fields, models
from odoo.exceptions import UserError

REPORTS = {
    "report_card": "horizonforge_school_gradebook.action_report_card",
    "reference": "horizonforge_school_gradebook.action_report_card_reference",
    "class_sheet": "horizonforge_school_gradebook.action_report_class_sheet",
    "progress": "horizonforge_school_gradebook.action_report_progress",
    "missing": "horizonforge_school_gradebook.action_report_missing",
}


class SchoolGradeReport(models.TransientModel):
    """Chooses what to print. The same ``_get_*`` data feeds the PDF and
    the CSV export, and every number comes from the grade engine."""

    _name = "school.grade.report"
    _description = "Grade Reports"

    report_type = fields.Selection(
        [
            ("report_card", "Report card"),
            ("reference", "Report card reference"),
            ("class_sheet", "Class grade sheet"),
            ("progress", "Progress report"),
            ("missing", "Missing work"),
        ],
        string="Report",
        default="report_card",
        required=True,
    )
    year_id = fields.Many2one(
        "school.year",
        string="School Year",
        required=True,
        default=lambda self: self.env["school.year"]._get_current(),
    )
    period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        compute="_compute_period_id",
        store=True,
        readonly=False,
        domain="[('year_id', '=', year_id)]",
        help="The report card also shows the periods before this one and "
        "the year grade so far.",
    )
    section_ids = fields.Many2many(
        "school.section",
        string="Classes",
        domain="[('year_id', '=', year_id)]",
        help="Leave empty for every class you can see.",
    )
    homeroom_id = fields.Many2one(
        "school.homeroom",
        string="Homeroom",
    )
    grade_level_id = fields.Many2one(
        "school.grade.level",
        string="Grade Level",
    )
    student_ids = fields.Many2many(
        "school.student",
        string="Students",
        help="Leave empty for every student of the homeroom, grade level or classes chosen.",
    )

    @api.depends("year_id")
    def _compute_period_id(self):
        today = fields.Date.context_today(self)
        for wizard in self:
            periods = wizard.year_id.period_ids
            wizard.period_id = (
                periods.filtered(lambda p: p.date_start <= today <= p.date_end)
                or periods.filtered(lambda p: p.date_end < today)[-1:]
                or periods[:1]
            )

    # ------------------------------------------------------------------
    # What to report on
    # ------------------------------------------------------------------

    def _get_sections(self):
        self.ensure_one()
        sections = self.section_ids or self.env["school.section"].search(
            [("year_id", "=", self.year_id.id)]
        )
        return sections.sorted(
            lambda s: (s.course_id.sequence, s.course_id.name or "", s.name or "", s.id)
        )

    def _get_students(self):
        """Chosen students, else those of the homeroom, grade level or
        classes chosen; in the year's classes the user can see."""
        self.ensure_one()
        enrolled = self._get_sections().enrollment_ids.student_id.with_context(active_test=False)
        students = enrolled
        if self.student_ids:
            students &= self.student_ids
        if self.homeroom_id:
            students = students.filtered(lambda s: s.homeroom_id == self.homeroom_id)
        if self.grade_level_id:
            students = students.filtered(lambda s: s.grade_level_id == self.grade_level_id)
        return students.sorted(
            lambda s: (
                s.grade_level_id.sequence, (s.last_name or "").lower(), (s.first_name or "").lower(), s.id,
            )
        )

    def _require_period(self):
        if not self.period_id:
            raise UserError(_("Choose a grading period."))

    @api.model
    def _score_text(self, score):
        """A score as the teacher entered it: 88%, 22/25, EX, M."""
        if not score:
            return ""
        if score.status == "excused":
            return _("EX")
        if score.status == "missing":
            return _("M")
        assignment = score.assignment_id
        value = f"{score.value_entered:g}"
        if assignment.entry_mode == "percent":
            return f"{value}%"
        if assignment.entry_mode == "wrong":
            return _("%(wrong)s wrong of %(max)s", wrong=value, max=f"{assignment.max_points:g}")
        return f"{value}/{assignment.max_points:g}"

    # ------------------------------------------------------------------
    # Report data
    # ------------------------------------------------------------------

    def _get_report_cards(self):
        """One page per student: every subject in course order, with the
        grade of each period so far and of the year."""
        self._require_period()
        Engine = self.env["school.grade.engine"]
        periods = self.year_id.period_ids.filtered(
            lambda p: p.date_start <= self.period_id.date_start
        )
        students = self._get_students()
        by_section = {}
        for section in self._get_sections():
            section_students = section.enrollment_ids.student_id.with_context(active_test=False) & students
            if not section_students:
                continue
            scored = section.grading_type == "percent"
            by_section[section] = {
                "periods": {
                    period: Engine._section_grades(section, period, section_students)
                    for period in periods
                } if scored else {},
                "year": Engine._section_year_grades(section, section_students, periods) if scored else {},
                "students": section_students,
                # Letters of letter-only courses, and report card comments.
                "marks": {
                    (mark.student_id.id, mark.period_id.id): mark
                    for mark in self.env["school.period.mark"].search([
                        ("section_id", "=", section.id),
                        ("period_id", "in", periods.ids),
                        ("student_id", "in", section_students.ids),
                    ])
                },
            }
        # Filled by the attendance addon when it is installed.
        attendance = [
            students._school_attendance_totals(period.date_start, period.date_end)
            for period in periods
        ]
        cards = []
        for student in students:
            rows = []
            for section, data in by_section.items():
                if student not in data["students"]:
                    continue
                marks = data["marks"]
                if section.grading_type == "percent":
                    grades = [
                        {
                            "grade": Engine._format(data["periods"][period][student.id]["grade"]),
                            "letter": data["periods"][period][student.id]["letter"],
                        }
                        for period in periods
                    ]
                    year = {
                        "grade": Engine._format(data["year"][student.id]["grade"]),
                        "letter": data["year"][student.id]["letter"],
                    }
                else:
                    # No percent: the teacher's letter (or nothing, for a
                    # comment-only course), and no year grade.
                    grades = [
                        {
                            "grade": "",
                            "letter": marks[student.id, period.id].letter or ""
                            if section.grading_type == "letter" and (student.id, period.id) in marks
                            else "",
                        }
                        for period in periods
                    ]
                    year = {"grade": "", "letter": ""}
                mark = marks.get((student.id, self.period_id.id))
                rows.append({
                    "section": section,
                    "grading_type": section.grading_type,
                    "course": section.course_id.name,
                    "teacher": section.teacher_id.name or "",
                    "grades": grades,
                    "year": year,
                    "comment": mark.comment or "" if mark else "",
                })
            if rows:
                totals = [period_totals.get(student.id) for period_totals in attendance]
                scales = self.env["school.grading.scale"]
                for row in rows:
                    if row["grading_type"] == "percent":
                        scales |= row["section"]._get_grading_scale(student)
                cards.append({
                    "student": student,
                    "periods": periods,
                    "rows": rows,
                    "attendance": self._attendance_lines(totals),
                    "attendance_totals": totals,
                    "scales": scales,
                })
        return cards

    def _get_card_pages(self):
        """The folded report card: the report card data laid out over all
        the year's grading periods, the later ones left blank."""
        all_periods = self.year_id.period_ids
        decimals = self.env.company.school_grade_decimals
        pages = []
        for card in self._get_report_cards():
            blank = len(all_periods) - len(card["periods"])
            subjects = []
            comments = []
            for row in card["rows"]:
                if row["comment"]:
                    comments.append({"course": row["course"], "comment": row["comment"]})
                if row["grading_type"] == "comment":
                    continue
                cells = [
                    grade["grade"] if row["grading_type"] == "percent" else grade["letter"]
                    for grade in row["grades"]
                ]
                subjects.append({
                    "course": row["course"],
                    "cells": cells + [""] * blank,
                    "average": row["year"]["grade"],
                })
            totals = card["attendance_totals"]
            has_attendance = any(totals)
            absences = [f"{t['absent']:g}" if t else "0" for t in totals] if has_attendance else []
            present = [f"{t['present']:g}" if t else "" for t in totals] if has_attendance else []
            pages.append({
                "student": card["student"],
                "periods": all_periods,
                "subjects": subjects,
                "comments": comments,
                "keys": [scale._get_key(decimals) for scale in card["scales"]],
                "absences": absences + [""] * (blank if has_attendance else len(all_periods)),
                "absences_total": f"{sum(t['absent'] for t in totals if t):g}" if has_attendance else "",
                "present": present + [""] * (blank if has_attendance else len(all_periods)),
                "present_total": f"{sum(t['present'] for t in totals if t):g}" if has_attendance else "",
            })
        return pages

    def _get_reference_sheets(self):
        """For copying grades onto a paper report card: one page per
        homeroom, a table per grade level, a row per student with this
        period's grade in each course (and the year grade so far)."""
        groups = {}
        for card in self._get_report_cards():
            student = card["student"]
            groups.setdefault(student.homeroom_id, {}).setdefault(student.grade_level_id, []).append(card)
        sheets = []
        for homeroom, levels in sorted(
            groups.items(), key=lambda item: (not item[0], item[0].name or "")
        ):
            tables = []
            for level, cards in sorted(levels.items(), key=lambda item: (item[0].sequence, item[0].name or "")):
                courses = []
                for card in cards:
                    for row in card["rows"]:
                        if row["grading_type"] != "comment" and row["course"] not in courses:
                            courses.append(row["course"])
                rows = []
                for card in cards:
                    by_course = {row["course"]: row for row in card["rows"]}
                    cells = []
                    for course in courses:
                        row = by_course.get(course)
                        if not row:
                            cells.append({"grade": "", "average": ""})
                            continue
                        grade = row["grades"][-1]
                        percent = row["grading_type"] == "percent"
                        cells.append({
                            "grade": grade["grade"] if percent else grade["letter"],
                            "average": row["year"]["grade"] if percent else "",
                        })
                    totals = card["attendance_totals"][-1] if card["attendance_totals"] else None
                    rows.append({
                        "student": card["student"],
                        "cells": cells,
                        "absent": f"{totals['absent']:g}" if totals else "",
                        "present": f"{totals['present']:g}" if totals else "",
                        "absent_year": f"{sum(t['absent'] for t in card['attendance_totals'] if t):g}"
                        if totals else "",
                        "present_year": f"{sum(t['present'] for t in card['attendance_totals'] if t):g}"
                        if totals else "",
                    })
                tables.append({"grade_level": level, "courses": courses, "rows": rows})
            sheets.append({"homeroom": homeroom, "tables": tables})
        return sheets

    @api.model
    def _attendance_lines(self, totals):
        """Report card attendance: a line per figure, a value per period
        and the total. Empty without the attendance addon."""
        if not any(totals):
            return []
        lines = []
        for key, label in (
            ("absent", _("Days absent")),
            ("excused", _("of which excused")),
            ("tardy", _("Times tardy")),
        ):
            values = [total[key] if total else 0 for total in totals]
            lines.append({
                "label": label,
                "values": [f"{value:g}" for value in values],
                "total": f"{sum(values):g}",
            })
        return lines

    def _get_class_sheets(self):
        """One page per class: each student's category averages, period
        grade and letter."""
        self._require_period()
        Engine = self.env["school.grade.engine"]
        decimals = self.env.company.school_display_decimals
        sheets = []
        for section in self._get_sections().filtered(lambda s: s.grading_type == "percent"):
            students = self._gradebook_students(section)
            if not students:
                continue
            grades = Engine._section_grades(section, self.period_id, students)
            _method, weights = Engine._weights(section)
            used = {c for grade in grades.values() for c in grade["categories"]}
            categories = self.env["school.score.category"].with_context(active_test=False).search(
                [("id", "in", list(used | set(weights or {})))]
            )
            sheets.append({
                "section": section,
                "categories": categories,
                "weights": {c.id: f"{(weights or {}).get(c.id, 0):g}%" if weights else "" for c in categories},
                "rows": [
                    {
                        "student": student,
                        "categories": [
                            Engine._format(grades[student.id]["categories"].get(c.id), decimals)
                            for c in categories
                        ],
                        "grade": Engine._format(grades[student.id]["grade"]),
                        "letter": grades[student.id]["letter"],
                    }
                    for student in students
                ],
                "average": Engine._format(Engine._class_average(grades), decimals),
            })
        return sheets

    def _gradebook_students(self, section):
        """Students of the class during the period, as in the grid."""
        period = self.period_id
        enrollments = section.enrollment_ids.filtered(
            lambda e: e.date_start <= period.date_end
            and (not e.date_end or e.date_end >= period.date_start)
        )
        students = enrollments.student_id.with_context(active_test=False)
        if self.student_ids:
            students &= self.student_ids
        return students.sorted(
            lambda s: ((s.last_name or "").lower(), (s.first_name or "").lower(), s.id)
        )

    def _get_progress_reports(self):
        """One page per student and class: every assignment of the period
        with its score, then the category averages and the period grade."""
        self._require_period()
        Engine = self.env["school.grade.engine"]
        decimals = self.env.company.school_display_decimals
        wanted = self._get_students()
        pages = []
        for section in self._get_sections().filtered(lambda s: s.grading_type == "percent"):
            students = self._gradebook_students(section) & wanted
            if not students:
                continue
            assignments = self.env["school.assignment"].search([
                ("section_id", "=", section.id), ("period_id", "=", self.period_id.id),
            ])
            scores = {
                (score.assignment_id.id, score.student_id.id): score
                for score in self.env["school.score"].search([
                    ("assignment_id", "in", assignments.ids), ("student_id", "in", students.ids),
                ])
            }
            grades = Engine._section_grades(section, self.period_id, students)
            for student in students:
                grade = grades[student.id]
                categories = self.env["school.score.category"].with_context(active_test=False).browse(
                    list(grade["categories"])
                ).sorted("sequence")
                pages.append({
                    "student": student,
                    "section": section,
                    "rows": [
                        {
                            "date": assignment.date,
                            "name": assignment.name,
                            "category": assignment.category_id.code,
                            "score": self._score_text(scores.get((assignment.id, student.id))),
                            "percent": Engine._format(
                                scores[assignment.id, student.id].percent, decimals
                            ) if scores.get((assignment.id, student.id))
                            and scores[assignment.id, student.id].status == "scored" else "",
                            "comment": scores[assignment.id, student.id].comment or ""
                            if scores.get((assignment.id, student.id)) else "",
                        }
                        for assignment in assignments
                    ],
                    "categories": [
                        {"name": c.name, "average": Engine._format(grade["categories"][c.id], decimals)}
                        for c in categories
                    ],
                    "grade": Engine._format(grade["grade"]),
                    "letter": grade["letter"],
                })
        pages.sort(key=lambda page: (
            (page["student"].last_name or "").lower(), (page["student"].first_name or "").lower(),
            page["student"].id, page["section"].course_id.sequence,
        ))
        return pages

    def _get_missing_work(self):
        """Per class, the students with scores marked missing and which
        assignments. Without a period: the whole year."""
        groups = []
        wanted = self._get_students() if (
            self.student_ids or self.homeroom_id or self.grade_level_id
        ) else None
        for section in self._get_sections():
            domain = [("section_id", "=", section.id), ("status", "=", "missing")]
            if self.period_id:
                domain.append(("period_id", "=", self.period_id.id))
            if wanted is not None:
                domain.append(("student_id", "in", wanted.ids))
            scores = self.env["school.score"].search(domain)
            if not scores:
                continue
            by_student = {}
            for score in scores.sorted(lambda s: (s.assignment_id.date, s.assignment_id.id)):
                by_student.setdefault(score.student_id, []).append(score.assignment_id)
            groups.append({
                "section": section,
                "rows": [
                    {"student": student, "assignments": assignments}
                    for student, assignments in sorted(
                        by_student.items(),
                        key=lambda item: ((item[0].last_name or "").lower(), (item[0].first_name or "").lower()),
                    )
                ],
                "count": len(scores),
            })
        return groups

    # ------------------------------------------------------------------
    # Output
    # ------------------------------------------------------------------

    def _check_not_empty(self):
        getter = {
            "report_card": self._get_report_cards,
            "reference": self._get_report_cards,
            "class_sheet": self._get_class_sheets,
            "progress": self._get_progress_reports,
            "missing": self._get_missing_work,
        }[self.report_type]
        if not getter():
            raise UserError(
                _("No missing work for this selection.") if self.report_type == "missing"
                else _("Nothing to report for this selection.")
            )

    def action_print(self):
        self.ensure_one()
        self._check_not_empty()
        # sudo: only system admins can read report actions
        return self.env.ref(REPORTS[self.report_type]).sudo().report_action(self, config=False)

    def _csv_rows(self):
        """Header and rows of the CSV export of the chosen report."""
        self.ensure_one()
        if self.report_type in ("report_card", "reference"):
            cards = self._get_report_cards()
            periods = cards[0]["periods"] if cards else self.env["school.period"]
            header = [_("Student ID"), _("Last Name"), _("First Name"), _("Grade Level"), _("Course"), _("Teacher")]
            for period in periods:
                header += [period.name, _("%(period)s Letter", period=period.name)]
            header += [_("Year"), _("Year Letter"), _("Comment")]
            rows = []
            for card in cards:
                student = card["student"]
                for row in card["rows"]:
                    line = [student.student_code or "", student.last_name, student.first_name,
                            student.grade_level_id.name or "", row["course"], row["teacher"]]
                    for grade in row["grades"]:
                        line += [grade["grade"], grade["letter"]]
                    rows.append(line + [row["year"]["grade"], row["year"]["letter"], row["comment"]])
            return header, rows
        if self.report_type == "class_sheet":
            sheets = self._get_class_sheets()
            categories = self.env["school.score.category"]
            for sheet in sheets:
                categories |= sheet["categories"]
            categories = categories.sorted("sequence")
            header = [_("Class"), _("Student ID"), _("Last Name"), _("First Name")]
            header += categories.mapped("name") + [_("Grade"), _("Letter")]
            rows = []
            for sheet in sheets:
                index = {c.id: i for i, c in enumerate(sheet["categories"])}
                for row in sheet["rows"]:
                    student = row["student"]
                    rows.append(
                        [sheet["section"].display_name, student.student_code or "",
                         student.last_name, student.first_name]
                        + [row["categories"][index[c.id]] if c.id in index else "" for c in categories]
                        + [row["grade"], row["letter"]]
                    )
            return header, rows
        if self.report_type == "progress":
            header = [_("Student ID"), _("Last Name"), _("First Name"), _("Class"), _("Date"),
                      _("Assignment"), _("Category"), _("Score"), _("Percent"), _("Comment")]
            rows = []
            for page in self._get_progress_reports():
                student = page["student"]
                for row in page["rows"]:
                    rows.append([
                        student.student_code or "", student.last_name, student.first_name,
                        page["section"].display_name, fields.Date.to_string(row["date"]),
                        row["name"], row["category"], row["score"], row["percent"], row["comment"],
                    ])
            return header, rows
        header = [_("Class"), _("Student ID"), _("Last Name"), _("First Name"), _("Date"), _("Assignment")]
        rows = []
        for group in self._get_missing_work():
            for row in group["rows"]:
                student = row["student"]
                for assignment in row["assignments"]:
                    rows.append([
                        group["section"].display_name, student.student_code or "", student.last_name,
                        student.first_name, fields.Date.to_string(assignment.date), assignment.name,
                    ])
        return header, rows

    def action_export_csv(self):
        self.ensure_one()
        self._check_not_empty()
        header, rows = self._csv_rows()
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        writer.writerows(rows)
        label = dict(self._fields["report_type"]._description_selection(self.env))[self.report_type]
        name = f"{label} {self.period_id.name or self.year_id.name}.csv".replace("/", "-")
        attachment = self.env["ir.attachment"].create({
            "name": name,
            # With a byte order mark, so Excel reads accents correctly.
            "datas": base64.b64encode(buffer.getvalue().encode("utf-8-sig")),
            "mimetype": "text/csv",
            "res_model": self._name,
            "res_id": self.id,
        })
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{attachment.id}?download=true",
            "target": "download",
        }
