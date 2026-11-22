from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import Form, tagged

from .common import SchoolCoreCase


@tagged("post_install", "-at_install")
class TestSchoolSetup(SchoolCoreCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Only the test's own records: other grade levels and homerooms
        # (demo data) would be promoted and generated too.
        cls.env["school.homeroom"].search([]).action_archive()
        cls.env["school.grade.level"].search(
            [("id", "not in", (cls.level_5 | cls.level_6).ids)]
        ).sequence = 0
        cls.homeroom = cls.env["school.homeroom"].create({
            "name": "Test Grades 5-6",
            "teacher_id": cls.teacher.id,
            "grade_level_ids": [Command.set((cls.level_5 | cls.level_6).ids)],
        })

    def test_student_homeroom_follows_grade_level(self):
        self.assertEqual((self.anna | self.ben | self.carl).homeroom_id, self.homeroom)
        level_7 = self.env["school.grade.level"].create({"name": "Test Grade 7", "sequence": 7})
        self.carl.grade_level_id = level_7
        self.assertFalse(self.carl.homeroom_id)
        # A grade level split over two homerooms: the choice is manual and kept.
        split = self.env["school.homeroom"].create({
            "name": "Test Grade 5 B",
            "grade_level_ids": [Command.set(self.level_5.ids)],
        })
        self.assertEqual(self.anna.homeroom_id, self.homeroom)
        dana = self.env["school.student"].create({
            "first_name": "Dana", "last_name": "Sample", "grade_level_id": self.level_5.id,
        })
        self.assertFalse(dana.homeroom_id)
        dana.homeroom_id = split
        self.assertEqual(dana.homeroom_id, split)

    def test_school_days(self):
        self.env["school.calendar.day"].create([
            {"year_id": self.year.id, "name": "Labor Day", "date_start": "2030-09-02"},
            {"year_id": self.year.id, "name": "Break",
             "date_start": "2030-09-05", "date_end": "2030-09-09"},
        ])
        days = self.year._get_school_days(date(2030, 8, 30), date(2030, 9, 11))
        self.assertEqual(days, [
            date(2030, 8, 30), date(2030, 9, 3), date(2030, 9, 4),
            date(2030, 9, 10), date(2030, 9, 11),
        ])
        # Clipped to the year.
        self.assertEqual(self.year._get_school_days(date(2030, 8, 1), date(2030, 8, 27)),
                         [date(2030, 8, 26), date(2030, 8, 27)])

    def test_generate_sections(self):
        music_teacher = self.other_teacher
        music = self.env["school.course"].create({
            "name": "Test Music",
            "grade_level_ids": [Command.set((self.level_5 | self.level_6).ids)],
            "teacher_id": music_teacher.id,
        })
        (self.section_5 | self.section_6).unlink()
        self.year.action_generate_sections()
        sections = self.year.section_ids
        self.assertEqual(sections.course_id, self.math_5 | self.math_6 | music)
        self.assertEqual(set(sections.mapped("homeroom_id")), {self.homeroom})
        by_course = {section.course_id: section for section in sections}
        self.assertEqual(by_course[self.math_5].teacher_id, self.teacher)
        self.assertEqual(by_course[self.math_5].homeroom_id, self.homeroom)
        self.assertEqual(by_course[music].teacher_id, music_teacher)
        # Students take the courses of their own grade level within the room.
        self.assertEqual(by_course[self.math_5].enrollment_ids.student_id, self.anna | self.ben)
        self.assertEqual(by_course[self.math_6].enrollment_ids.student_id, self.carl)
        self.assertEqual(by_course[music].enrollment_ids.student_id, self.anna | self.ben | self.carl)
        # Running it again creates nothing.
        self.year.action_generate_sections()
        self.assertEqual(len(self.year.section_ids), 3)

    def test_enroll_only_own_homeroom(self):
        other_room = self.env["school.homeroom"].create({
            "name": "Test Grade 5 B",
            "grade_level_ids": [Command.set(self.level_5.ids)],
        })
        self.ben.homeroom_id = other_room
        self.section_5.homeroom_id = self.homeroom
        self.section_5.action_enroll_grade_levels()
        self.assertEqual(self.section_5.enrollment_ids.student_id, self.anna)

    def test_new_year_setup(self):
        self.section_5.homeroom_id = self.homeroom
        self.section_6.write({"homeroom_id": self.homeroom.id, "name": "A"})
        (self.section_5 | self.section_6).action_enroll_grade_levels()
        self.env["school.calendar.day"].create({
            "year_id": self.year.id, "name": "Fall break",
            "date_start": "2030-10-14", "date_end": "2030-10-15",
        })
        wizard = Form(self.env["school.year.setup"])
        self.assertEqual(wizard.source_year_id, self.year)
        self.assertEqual(wizard.period_mode, "copy")
        self.assertEqual(wizard.name, "2031-32")
        self.assertEqual(wizard.date_start, date(2031, 8, 25))
        self.assertEqual(wizard.date_end, date(2032, 5, 21))
        wizard = wizard.save()
        self.assertEqual(wizard.graduate_ids, self.carl)
        action = wizard.action_confirm()
        year = self.env["school.year"].browse(action["res_id"])

        self.assertTrue(year.is_current)
        self.assertFalse(self.year.is_current)
        self.assertEqual(year.period_ids.mapped("name"), ["Semester 1", "Semester 2"])
        self.assertEqual(year.period_ids[0].date_start, date(2031, 8, 25))
        self.assertEqual(year.period_ids[0].date_end, date(2032, 1, 9))
        self.assertEqual(year.period_ids[1].date_end, date(2032, 5, 21))
        # Days off come along, 52 weeks later (the same weekdays).
        days_off = year.day_off_ids.filtered(lambda d: d.day_type == "off")
        self.assertEqual(
            days_off.mapped(lambda d: (d.name, d.date_start, d.date_end)),
            [("Fall break", date(2031, 10, 13), date(2031, 10, 14))],
        )

        # Carl graduated, Anna and Ben moved up to grade 6.
        self.assertFalse(self.carl.active)
        self.assertEqual((self.anna | self.ben).grade_level_id, self.level_6)

        self.assertEqual(len(year.section_ids), 2)
        by_course = {section.course_id: section for section in year.section_ids}
        self.assertEqual(by_course[self.math_6].name, "A")
        self.assertEqual(by_course[self.math_6].teacher_id, self.other_teacher)
        self.assertEqual(by_course[self.math_6].enrollment_ids.student_id, self.anna | self.ben)
        self.assertEqual(set(by_course[self.math_6].enrollment_ids.mapped("date_start")), {year.date_start})
        self.assertFalse(by_course[self.math_5].enrollment_ids)
        # Last year's enrollments are untouched.
        self.assertEqual(self.section_5.enrollment_ids.student_id, self.anna | self.ben)

    def test_new_year_setup_from_homerooms(self):
        wizard = self.env["school.year.setup"].create({
            "class_mode": "homeroom",
            "promote_students": False,
            "make_current": False,
        })
        year = self.env["school.year"].browse(wizard.action_confirm()["res_id"])
        self.assertFalse(year.is_current)
        self.assertEqual(self.anna.grade_level_id, self.level_5)
        self.assertTrue(self.carl.active)
        self.assertEqual(year.section_ids.course_id, self.math_5 | self.math_6)
        self.assertEqual(set(year.section_ids.mapped("teacher_id")), {self.teacher})
        self.assertEqual(
            year.section_ids.enrollment_ids.student_id, self.anna | self.ben | self.carl
        )

    def test_generate_six_periods_ending_friday(self):
        wizard = self.env["school.year.setup"].create({
            "name": "Test 2031-32",
            "date_start": "2031-08-18",   # a Monday
            "date_end": "2032-05-21",     # a Friday, 40 weeks later
            "period_mode": "generate",
            "period_count": 6,
            "period_name": "Six Weeks",
            "class_mode": "none",
            "promote_students": False,
            "make_current": False,
        })
        year = self.env["school.year"].browse(wizard.action_confirm()["res_id"])
        periods = year.period_ids
        self.assertEqual(periods.mapped("name"), [f"Six Weeks {n}" for n in range(1, 7)])
        self.assertEqual(periods[0].date_start, year.date_start)
        self.assertEqual(periods[-1].date_end, year.date_end)
        self.assertEqual({p.date_end.weekday() for p in periods}, {4})        # Fridays
        self.assertEqual({p.date_start.weekday() for p in periods}, {0})      # Mondays
        lengths = [(p.date_end - p.date_start).days + 3 for p in periods]
        self.assertEqual({length % 7 for length in lengths}, {0})             # whole weeks
        self.assertLessEqual(max(lengths) - min(lengths), 7)                  # 6 or 7 weeks each

    def test_first_year_without_source(self):
        self.env["school.year"].search([]).is_current = False
        wizard = self.env["school.year.setup"].create({
            "source_year_id": False,
            "name": "First",
            "date_start": "2032-08-16",
            "date_end": "2033-05-20",
            "class_mode": "homeroom",
            "promote_students": False,
        })
        self.assertEqual(wizard.period_mode, "generate")
        year = self.env["school.year"].browse(wizard.action_confirm()["res_id"])
        self.assertEqual(len(year.period_ids), 6)
        self.assertTrue(year.is_current)
        self.assertEqual(year.section_ids.course_id, self.math_5 | self.math_6)

    def test_setup_guide(self):
        guide = self.env["school.setup.guide"].create({})
        self.assertEqual(guide.year_id, self.year)
        self.assertEqual(guide.period_count, 2)
        self.assertEqual(guide.section_count, 2)
        self.assertEqual(guide.action_year()["res_id"], self.year.id)
        self.assertEqual(guide.action_calendar()["domain"], [("year_id", "=", self.year.id)])
        self.assertEqual(guide.action_homerooms()["res_model"], "school.homeroom")
        (self.section_5 | self.section_6).unlink()
        guide.action_generate_sections()
        self.assertEqual(len(self.year.section_ids), 2)
        self.year.is_current = False
        self.assertEqual(guide.action_year()["res_model"], "school.year.setup")

    def test_office_edits_calendar(self):
        day = self.env["school.calendar.day"].with_user(self.office).create({
            "name": "Snow day", "date_start": "2031-01-20",
        })
        self.assertEqual(day.year_id, self.year)
        self.assertEqual(day.date_end, day.date_start)
        day.unlink()

    def test_calendar_views(self):
        action = self.year.action_open_calendar()
        self.assertEqual(action["view_mode"], "calendar,list")
        Day = self.env["school.calendar.day"].with_user(self.office)
        arch = Day.get_view(view_type="calendar")["arch"]
        self.assertIn('date_stop="date_end"', arch)
        Day.get_view(view_type="list")
        Day.get_view(view_type="form")

    def test_day_off_inside_year(self):
        with self.assertRaises(ValidationError):
            self.env["school.calendar.day"].create({
                "year_id": self.year.id, "name": "Wrong year", "date_start": "2029-12-25",
            })

    def test_easter_dates(self):
        Year = self.env["school.year"]
        self.assertEqual(Year._easter(2026), date(2026, 4, 5))
        self.assertEqual(Year._easter(2027), date(2027, 3, 28))
        self.assertEqual(Year._easter(2030), date(2030, 4, 21))
        self.assertEqual(dict(Year._holidays(2026)), {
            "Good Friday": date(2026, 4, 3), "Easter": date(2026, 4, 5),
            "Thanksgiving": date(2026, 11, 26), "Christmas": date(2026, 12, 25),
        })

    def test_holidays_shown_only(self):
        # Added when the year is created: those that fall inside it.
        holidays = self.year.day_off_ids.filtered(lambda d: d.day_type == "info")
        self.assertEqual(holidays.mapped(lambda d: (d.name, d.date_start)), [
            ("Thanksgiving", date(2030, 11, 28)), ("Christmas", date(2030, 12, 25)),
            ("Good Friday", date(2031, 4, 11)), ("Easter", date(2031, 4, 13)),
        ])
        self.assertEqual(set(holidays.mapped("color")), {10})
        # Shown only: school is in session, until a day off says otherwise.
        thanksgiving = date(2030, 11, 28)
        self.assertEqual(self.year._get_school_days(thanksgiving, thanksgiving), [thanksgiving])
        holidays[0].day_type = "off"
        self.assertEqual(self.year._get_school_days(thanksgiving, thanksgiving), [])
        # Adding again changes nothing; a deleted one comes back.
        self.assertFalse(self.year._add_holidays())
        holidays[1].unlink()
        self.assertEqual(self.year._add_holidays().name, "Christmas")
        # The setup guide counts the days off only.
        self.assertEqual(self.env["school.setup.guide"].create({}).day_off_count, 1)

    def test_name_order(self):
        students = self.anna | self.ben | self.carl
        self.carl.first_name = "Aaron"
        Student = self.env["school.student"].with_user(self.office)
        rows = Student.browse(students.ids)._grid_rows()
        self.assertEqual([r["name"] for r in rows], ["Example, Anna", "Example, Ben", "Sample, Aaron"])
        Student.grid_set_name_order("first_last")
        self.assertEqual(self.office.school_name_order, "first_last")
        rows = Student.browse(students.ids)._grid_rows()
        self.assertEqual([r["name"] for r in rows], ["Aaron Sample", "Anna Example", "Ben Example"])
        # Each user keeps their own choice.
        self.assertEqual(self.teacher.school_name_order, "last_first")

    def test_patron_form_is_slim(self):
        action = self.env["ir.actions.act_window"]._for_xml_id("horizonforge_school_core.school_patron_action")
        form_id = [view_id for view_id, mode in action["views"] if mode == "form"][0]
        self.assertEqual(form_id, self.env.ref("horizonforge_school_core.school_patron_view_form").id)
        arch = self.env["res.partner"].with_user(self.office).get_view(form_id, "form")["arch"]
        for wanted in ("relationship", "phone", "student_ids"):
            self.assertIn(f'name="{wanted}"', arch)
        for unwanted in ("vat", "property_account", "sale", "purchase", "category_id", "company_type"):
            self.assertNotIn(unwanted, arch)

    def test_runs_without_contacts_and_discuss(self):
        module = self.env["ir.module.module"].search([("name", "=", "horizonforge_school_core")])
        self.assertEqual(set(module.dependencies_id.mapped("name")), {"base", "web"})
