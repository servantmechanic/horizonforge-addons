from datetime import date

from psycopg2 import IntegrityError

from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from odoo.addons.horizonforge_school_core.tests.common import SchoolCoreCase, assert_search_filters


@tagged("post_install", "-at_install")
class TestAttendance(SchoolCoreCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        ref = cls.env.ref
        cls.absent = ref("horizonforge_school_attendance.attendance_code_absent")
        cls.excused = ref("horizonforge_school_attendance.attendance_code_excused")
        cls.half = ref("horizonforge_school_attendance.attendance_code_half")
        cls.tardy = ref("horizonforge_school_attendance.attendance_code_tardy")
        cls.homeroom = cls.env["school.homeroom"].create({
            "name": "Test Lower Room",
            "teacher_id": cls.teacher.id,
            "grade_level_ids": [Command.set(cls.level_5.ids)],
        })
        cls.other_homeroom = cls.env["school.homeroom"].create({
            "name": "Test Upper Room",
            "teacher_id": cls.other_teacher.id,
            "grade_level_ids": [Command.set(cls.level_6.ids)],
        })
        (cls.section_5 | cls.section_6).action_enroll_grade_levels()
        cls.env["school.calendar.day"].create({
            "year_id": cls.year.id, "name": "Labor Day", "date_start": "2030-09-02",
        })
        cls.Attendance = cls.env["school.attendance"]
        cls.semester_1 = cls.year.period_ids[0]

    def _record(self, student, day, code=None, user=None, **vals):
        return self.Attendance.with_user(user or self.teacher).create({
            "student_id": student.id, "date": day, "code_id": (code or self.absent).id, **vals,
        })

    def _change(self, student, day, code=None, note=""):
        return {"student_id": student.id, "date": day, "code_id": code.id if code else False, "note": note}

    # Records

    def test_codes(self):
        self.assertEqual((self.absent.absence_days, self.half.absence_days, self.tardy.absence_days), (1, 0.5, 0))
        code = self.env["school.attendance.code"].create({"name": "Field trip", "code": "f"})
        self.assertEqual((code.code, code.kind, code.absence_days), ("F", "absent", 1))
        code.kind = "tardy"
        self.assertEqual(code.absence_days, 0)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env["school.attendance.code"].create({"name": "Again", "code": "A"})

    def test_one_line_per_day(self):
        record = self._record(self.anna, "2030-09-03")
        self.assertEqual(record.recorded_by, self.teacher)
        self.assertEqual(record.homeroom_id, self.homeroom)
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self._record(self.anna, "2030-09-03", self.tardy)

    def test_grade_level_and_period(self):
        record = self._record(self.anna, "2030-09-03")
        self.assertEqual(record.grade_level_id, self.anna.grade_level_id)
        self.assertEqual(record.period_id, self.semester_1)
        # The grade level is the one at the time: moving up doesn't change it.
        self.anna.grade_level_id = self.level_6
        self.assertEqual(record.grade_level_id, self.level_5)
        # Same for the homeroom; the new teacher still sees the line.
        self.anna.homeroom_id = self.other_homeroom
        self.assertEqual(record.homeroom_id, self.homeroom)
        self.assertIn(record, self.Attendance.with_user(self.other_teacher).search([]))
        # Changing the grading periods moves the line to its new period.
        semester_2 = self.year.period_ids[1]
        self.semester_1.date_end = "2030-08-30"
        semester_2.date_start = "2030-09-02"
        self.assertEqual(record.period_id, semester_2)
        lines = self.Attendance.search([("period_id", "=", semester_2.id)])
        self.assertIn(record, lines)

    def test_search_filters(self):
        """Every filter of the Absences & Tardies search view runs."""
        self._record(self.anna, "2030-09-03")
        assert_search_filters(self, self.Attendance.with_user(self.teacher))

    def test_list_opener(self):
        action = self.Attendance.with_user(self.teacher).action_open_list()
        self.assertEqual(action["context"]["search_default_my_homeroom"], 1)
        self.assertEqual(action["context"]["search_default_current_year"], 1)
        action = self.Attendance.with_user(self.office).action_open_list()
        self.assertNotIn("search_default_my_homeroom", action["context"])

    def test_school_days_only(self):
        for day in ("2030-09-01", "2030-09-02", "2029-09-03"):  # Sunday, Labor Day, no school year
            with self.assertRaises(ValidationError):
                self._record(self.anna, day)

    def test_locked_period(self):
        record = self._record(self.anna, "2030-09-03")
        self.semester_1.locked = True
        with self.assertRaises(UserError):
            record.with_user(self.teacher).code_id = self.excused
        with self.assertRaises(UserError):
            self._record(self.ben, "2030-09-03")
        with self.assertRaises(UserError):
            record.with_user(self.teacher).unlink()
        record.with_user(self.admin).code_id = self.excused
        self.assertEqual(record.recorded_by, self.admin)

    # Totals

    def test_totals_assume_present(self):
        self._record(self.anna, "2030-09-03")                       # absent
        self._record(self.anna, "2030-09-04", self.excused)         # excused
        self._record(self.anna, "2030-09-05", self.half)            # half day
        self._record(self.anna, "2030-09-06", self.tardy)
        self._record(self.anna, "2030-09-09", self.tardy)
        # Aug 26 to Sep 13 2030: 15 weekdays less Labor Day.
        totals = self.Attendance._totals(self.anna | self.ben, date(2030, 8, 26), date(2030, 9, 13))
        # The test year is in the future: no school day has passed yet.
        self.assertEqual(totals[self.anna.id]["absent"], 2.5)
        self.assertEqual(totals[self.anna.id]["excused"], 1)
        self.assertEqual(totals[self.anna.id]["unexcused"], 1.5)
        self.assertEqual(totals[self.anna.id]["tardy"], 2)
        self.assertEqual(totals[self.ben.id]["absent"], 0)
        self.assertEqual(self.anna._school_attendance_totals(date(2030, 9, 4), date(2030, 9, 4))[self.anna.id]["absent"], 1)

    def test_totals_count_days_up_to_today(self):
        from odoo import fields
        today = fields.Date.context_today(self.env.user)
        year = self.env["school.year"].create({
            "name": "Test Now",
            "date_start": today.replace(month=1, day=1),
            "date_end": today.replace(month=12, day=31),
        }) if not self.Attendance._year_for(today) else self.Attendance._year_for(today)
        days = year._get_school_days(year.date_start, today)
        if not days:
            self.skipTest("no school day so far this year")
        self._record(self.anna, days[-1], self.half, user=self.admin)
        totals = self.Attendance._totals(self.anna, year.date_start, year.date_end)[self.anna.id]
        self.assertEqual(totals["school_days"], len(days))
        self.assertEqual(totals["present"], len(days) - 0.5)

    # Grid

    def test_grid_week(self):
        self._record(self.anna, "2030-09-03", note="Sick")
        data = self.Attendance.with_user(self.teacher).attendance_open(False, "2030-09-04", "week")
        self.assertEqual(data["homeroom_id"], self.homeroom.id)
        self.assertEqual([h["id"] for h in data["homerooms"]], self.homeroom.ids)
        self.assertEqual([d["date"] for d in data["days"]],
                         ["2030-09-02", "2030-09-03", "2030-09-04", "2030-09-05", "2030-09-06"])
        self.assertEqual([d["off"] for d in data["days"]], [True, False, False, False, False])
        self.assertEqual(data["days"][0]["off_name"], "Labor Day")
        self.assertEqual([s["name"] for s in data["students"]], ["Example, Anna", "Example, Ben"])
        self.assertEqual(data["records"], [{
            "student_id": self.anna.id, "date": "2030-09-03", "code_id": self.absent.id, "note": "Sick",
        }])
        self.assertEqual(data["totals"][self.anna.id], {"absent": "1", "tardy": "0"})
        self.assertEqual(data["period_name"], "Semester 1")
        self.assertTrue(data["can_edit"])
        self.assertEqual({c["code"] for c in data["codes"]} >= {"A", "E", "H", "X", "T"}, True)

    def test_grid_period_mode(self):
        self.semester_1.date_end = "2030-09-13"
        data = self.Attendance.with_user(self.teacher).attendance_open(self.homeroom.id, "2030-09-04", "period")
        self.assertEqual(len(data["days"]), 15)
        self.assertEqual(data["days"][0]["date"], "2030-08-26")
        self.assertEqual(sum(d["off"] for d in data["days"]), 1)

    def test_grid_access(self):
        Attendance = self.Attendance
        # A teacher without a homeroom has nothing to take.
        data = Attendance.with_user(self.admin).attendance_open()
        self.assertTrue({self.homeroom.id, self.other_homeroom.id} <= {h["id"] for h in data["homerooms"]})
        office = Attendance.with_user(self.office).attendance_open(self.other_homeroom.id, "2030-09-04")
        self.assertTrue(office["can_edit"])
        peek = Attendance.with_user(self.teacher).attendance_open(self.other_homeroom.id, "2030-09-04")
        self.assertFalse(peek["can_edit"])
        self.semester_1.locked = True
        locked = Attendance.with_user(self.teacher).attendance_open(self.homeroom.id, "2030-09-04")
        self.assertFalse(locked["can_edit"])
        self.assertTrue(locked["locked"])

    def test_save_batch(self):
        Attendance = self.Attendance.with_user(self.teacher)
        result = Attendance.save_batch([
            self._change(self.anna, "2030-09-03", self.absent),
            self._change(self.ben, "2030-09-03", self.tardy, "Bus late"),
            self._change(self.anna, "2030-09-04", self.half),
        ], "2030-08-26", "2031-01-10")
        self.assertFalse(result["errors"])
        self.assertEqual(len(result["saved"]), 3)
        self.assertEqual(result["totals"][self.anna.id], {"absent": "1.5", "tardy": "0"})
        self.assertEqual(result["totals"][self.ben.id], {"absent": "0", "tardy": "1"})
        # Change a code, clear a day (present again), clear an empty day.
        result = Attendance.save_batch([
            self._change(self.anna, "2030-09-03", self.excused),
            self._change(self.anna, "2030-09-04"),
            self._change(self.ben, "2030-09-05"),
        ], "2030-08-26", "2031-01-10")
        self.assertFalse(result["errors"])
        self.assertEqual(result["totals"][self.anna.id], {"absent": "1", "tardy": "0"})
        records = self.Attendance.search([("student_id", "in", (self.anna | self.ben).ids)])
        self.assertEqual(
            sorted(records.mapped(lambda r: (r.student_id.first_name, r.code_id.code, r.note or ""))),
            [("Anna", "E", ""), ("Ben", "T", "Bus late")],
        )

    def test_save_batch_refusals(self):
        result = self.Attendance.with_user(self.teacher).save_batch([
            self._change(self.anna, "2030-09-02", self.absent),   # Labor Day
            self._change(self.carl, "2030-09-03", self.absent),   # not this teacher's homeroom
            self._change(self.ben, "2030-09-03", self.absent),
        ])
        self.assertEqual([c["student_id"] for c in result["saved"]], self.ben.ids)
        self.assertEqual([e["student_id"] for e in result["errors"]], [self.anna.id, self.carl.id])
        self.assertIn("school day", result["errors"][0]["message"])

    # Security

    def test_teacher_own_homeroom_only(self):
        mine = self._record(self.anna, "2030-09-03")
        theirs = self._record(self.carl, "2030-09-03", user=self.other_teacher)
        Attendance = self.Attendance.with_user(self.teacher)
        self.assertEqual(Attendance.search([("date", "=", "2030-09-03")]), mine)
        with self.assertRaises(AccessError):
            theirs.with_user(self.teacher).code_id = self.excused
        with self.assertRaises(AccessError):
            self._record(self.carl, "2030-09-04")
        office = self.Attendance.with_user(self.office)
        self.assertEqual(office.search([("date", "=", "2030-09-03")]), mine | theirs)
        theirs.with_user(self.office).code_id = self.excused
        with self.assertRaises(AccessError):
            self.absent.with_user(self.office).name = "Changed"

    # Reports

    def test_summary_report(self):
        self.env.company.external_report_layout_id = self.env.ref("web.external_layout_standard")
        self._record(self.anna, "2030-09-03")
        self._record(self.anna, "2030-09-04", self.excused)
        self._record(self.ben, "2030-09-05", self.tardy)
        wizard = self.env["school.attendance.report"].create({
            "year_id": self.year.id, "period_id": self.semester_1.id, "homeroom_id": self.homeroom.id,
        })
        self.assertEqual((wizard.date_from, wizard.date_to), (self.semester_1.date_start, self.semester_1.date_end))
        anna, ben = wizard._get_rows()
        self.assertEqual((anna["absent"], anna["excused"], anna["unexcused"], anna["tardy"]), ("2", "1", "1", 0))
        self.assertEqual((ben["absent"], ben["tardy"]), ("0", 1))
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_school_attendance.report_attendance_summary", wizard.ids
        )[0].decode()
        self.assertIn("Attendance Summary", html)
        self.assertIn("Example, Anna", html)
        header, rows = wizard._csv_rows()
        self.assertEqual(header[-4:], ["Absent", "Excused", "Unexcused", "Tardy"])
        self.assertEqual(rows[0][-4:], ["2", "1", "1", 0])
        self.assertEqual(wizard.action_print()["report_name"],
                         "horizonforge_school_attendance.report_attendance_summary")
        self.assertIn("/web/content/", wizard.action_export_csv()["url"])
        own_dates = self.env["school.attendance.report"].create({
            "year_id": self.year.id, "date_from": "2030-09-04", "date_to": "2030-09-04",
            "student_ids": self.anna.ids,
        })
        self.assertEqual(own_dates._get_rows()[0]["absent"], "1")

    def test_report_card_attendance(self):
        if "school.grade.report" not in self.env:
            self.skipTest("gradebook not installed")
        homework = self.env.ref("horizonforge_school_gradebook.score_category_homework")
        assignment = self.env["school.assignment"].create({
            "section_id": self.section_5.id, "name": "Lesson", "date": "2030-09-03",
            "category_id": homework.id,
        })
        self.env["school.score"].create({
            "assignment_id": assignment.id, "student_id": self.anna.id, "value_entered": 90,
        })
        self._record(self.anna, "2030-09-04", self.excused)
        self._record(self.anna, "2030-09-05", self.half)
        self._record(self.anna, "2030-09-06", self.tardy)
        self.env.company.external_report_layout_id = self.env.ref("web.external_layout_standard")
        wizard = self.env["school.grade.report"].create({
            "year_id": self.year.id, "period_id": self.semester_1.id, "student_ids": self.anna.ids,
        })
        card, = wizard._get_report_cards()
        self.assertEqual(card["attendance"], [
            {"label": "Days absent", "values": ["1.5"], "total": "1.5"},
            {"label": "of which excused", "values": ["1"], "total": "1"},
            {"label": "Times tardy", "values": ["1"], "total": "1"},
        ])
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_school_gradebook.report_card", wizard.ids
        )[0].decode()
        self.assertIn("Days absent", html)

    def test_setup_guide_step(self):
        guide = self.env["school.setup.guide"].create({})
        self.assertGreaterEqual(guide.attendance_code_count, 5)
        self.assertEqual(guide.action_attendance_codes()["res_model"], "school.attendance.code")
        self.assertIn("step_attendance_codes", self.env["school.setup.guide"].get_view(view_type="form")["arch"])

    def test_demo_loader(self):
        self.env["school.year"]._load_school_demo()
        before = self.Attendance.search_count([])
        self.Attendance.search([]).unlink()
        self.env["school.year"]._load_school_attendance_demo()
        demo_year = self.env["school.year"].search([("name", "=", "2026-27")])
        records = self.Attendance.search([])
        self.assertTrue(records or before == 0)
        self.assertTrue(all(demo_year.date_start <= r.date <= demo_year.date_end for r in records))
