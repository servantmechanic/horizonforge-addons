from datetime import date

from odoo import Command
from odoo.exceptions import ValidationError
from odoo.tests import new_test_user, tagged

from .common import SchoolCoreCase


@tagged("post_install", "-at_install")
class TestSchoolDaysTarget(SchoolCoreCase):
    """A target of school days plus planned snow days sets the last day."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # Starts on Monday 2032-08-23. One period running to the end date.
        cls.days_year = cls.env["school.year"].create({
            "name": "Test Days 2032-33",
            "date_start": "2032-08-23",
            "date_end": "2033-05-27",
            "period_ids": [Command.create({
                "name": "Whole Year", "date_start": "2032-08-23", "date_end": "2033-05-27",
            })],
        })
        cls.days_year.day_off_ids.unlink()  # the holidays are shown only anyway

    def _day_off(self, day, user=None, **vals):
        return self.env["school.calendar.day"].with_user(user or self.env.user).create({
            "year_id": self.days_year.id, "name": "Off", "date_start": day, **vals,
        })

    def test_target_sets_end_date(self):
        year = self.days_year
        year.write({"school_days_target": 20, "snow_day_allowance": 3})
        # The 23rd weekday from the start.
        self.assertEqual(year.date_end, date(2032, 9, 22))
        self.assertEqual(year.period_ids.date_end, date(2032, 9, 22), "the last period follows")
        self.assertEqual(year.school_day_count, 23)

    def test_planned_day_off_moves_end_date(self):
        year = self.days_year
        year.write({"school_days_target": 20, "snow_day_allowance": 3})
        self._day_off("2032-09-06")  # Labor Day
        self.assertEqual(year.date_end, date(2032, 9, 23))

    def test_snow_days_use_the_allowance_first(self):
        year = self.days_year
        year.write({"school_days_target": 20, "snow_day_allowance": 3})
        self._day_off("2032-09-06")
        # A teacher adds a snow day: one of the three planned ones.
        snow = self._day_off("2032-09-07", user=self.teacher, name="Ice", is_snow_day=True)
        self.assertEqual(year.snow_days_used, 1)
        self.assertEqual(year.date_end, date(2032, 9, 23), "still within the allowance")
        # Three more: one past the allowance, the year runs a day longer.
        snow.date_end = "2032-09-10"
        self.assertEqual(year.snow_days_used, 4)
        self.assertEqual(year.date_end, date(2032, 9, 24))
        self.assertEqual(year.period_ids.date_end, date(2032, 9, 24))
        # Taking a snow day back shortens it again.
        snow.with_user(self.teacher).date_end = "2032-09-09"
        self.assertEqual(year.date_end, date(2032, 9, 23))
        snow.with_user(self.teacher).unlink()
        self.assertEqual(year.date_end, date(2032, 9, 23), "back within the allowance")

    def test_no_target_keeps_end_date(self):
        self._day_off("2032-09-06")
        self.assertEqual(self.days_year.date_end, date(2033, 5, 27))

    def test_snow_day_is_a_day_off(self):
        with self.assertRaises(ValidationError):
            self._day_off("2032-09-07", day_type="info", is_snow_day=True)

    def test_new_year_skips_snow_days(self):
        self.days_year.write({"school_days_target": 20, "snow_day_allowance": 3})
        self._day_off("2032-09-06", name="Labor Day")
        self._day_off("2032-09-07", name="Ice", is_snow_day=True)
        wizard = self.env["school.year.setup"].create({"source_year_id": self.days_year.id})
        self.assertEqual(wizard.school_days_target, 20)
        self.assertEqual(wizard.snow_day_allowance, 3)
        names = [command[2]["name"] for command in wizard._day_off_vals()]
        self.assertEqual(names, ["Labor Day"])


@tagged("post_install", "-at_install")
class TestCalendarAudience(SchoolCoreCase):
    """Teachers edit the calendar; entries can be for some people only."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year.day_off_ids.unlink()
        cls.homeroom = cls.env["school.homeroom"].create({
            "name": "Test Upper Room", "teacher_id": cls.other_teacher.id,
        })
        Day = cls.env["school.calendar.day"]
        base = {"year_id": cls.year.id, "date_start": "2030-10-16", "day_type": "info"}
        cls.everyone = Day.create({**base, "name": "Picture Day"})
        cls.grade_5 = Day.create({
            **base, "name": "Zoo Trip", "audience": "grade_level",
            "grade_level_ids": [Command.set(cls.level_5.ids)],
        })
        cls.grade_6 = Day.create({
            **base, "name": "Museum Trip", "audience": "grade_level",
            "grade_level_ids": [Command.set(cls.level_6.ids)],
        })
        cls.room = Day.create({
            **base, "name": "Room Party", "audience": "homeroom",
            "homeroom_ids": [Command.set(cls.homeroom.ids)],
        })
        cls.mine = Day.create({
            **base, "name": "Workshop", "audience": "teacher",
            "teacher_ids": [Command.set(cls.teacher.ids)],
        })

    def _for_me(self, user):
        return self.env["school.calendar.day"].with_user(user).search([
            ("year_id", "=", self.year.id), ("is_for_me", "=", True),
        ])

    def test_for_me(self):
        # Teaches Math 5 (grade 5).
        self.assertEqual(self._for_me(self.teacher), self.everyone | self.grade_5 | self.mine)
        # Teaches Math 6 (grade 6) and the homeroom.
        self.assertEqual(self._for_me(self.other_teacher), self.everyone | self.grade_6 | self.room)
        self.assertTrue(self.grade_5.with_user(self.teacher).is_for_me)
        self.assertFalse(self.grade_6.with_user(self.teacher).is_for_me)

    def test_audience_label(self):
        self.assertFalse(self.everyone.audience_label)
        self.assertEqual(self.grade_5.audience_label, "Test Grade 5")
        entries = {row["name"] for row in self.year._get_calendar_entries()}
        self.assertIn("Zoo Trip (Test Grade 5)", entries)

    def test_day_off_is_for_everyone(self):
        with self.assertRaises(ValidationError):
            self.env["school.calendar.day"].create({
                "year_id": self.year.id, "name": "Grade 5 off", "date_start": "2030-10-17",
                "audience": "grade_level", "grade_level_ids": [Command.set(self.level_5.ids)],
            })

    def test_teacher_edits_calendar(self):
        Day = self.env["school.calendar.day"].with_user(self.teacher)
        trip = Day.create({
            "year_id": self.year.id, "name": "Farm Trip", "date_start": "2030-10-18", "day_type": "info",
        })
        trip.name = "Dairy Farm Trip"
        trip.unlink()
        self.everyone.with_user(self.teacher).name = "School Pictures"
        menu = self.env.ref("horizonforge_school_core.menu_school_calendar")
        self.assertFalse(menu.group_ids)


@tagged("post_install", "-at_install")
class TestCourseCopyAndPreferences(SchoolCoreCase):

    def test_duplicate_course(self):
        copy = self.math_5.copy()
        self.assertEqual(copy.name, "Test Math 5 (copy)")
        self.assertFalse(copy.code)
        self.assertEqual(copy.grade_level_ids, self.level_5)
        self.assertFalse(copy.section_ids)

    def test_school_default_name_order(self):
        self.env.company.school_name_order = "first_last"
        user = new_test_user(
            self.env, login="school_new_teacher",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        self.assertEqual(user.school_name_order, "first_last")
        # Each teacher changes their own.
        user.with_user(user).school_name_order = "last_first"
        self.assertEqual(user.school_name_order, "last_first")

    def test_my_preferences_action(self):
        action = self.env.ref("horizonforge_school_core.action_school_my_preferences")
        result = action.with_user(self.teacher).run()
        self.assertEqual(result["res_model"], "res.users")
        self.assertEqual(result["res_id"], self.teacher.id)
        self.assertEqual(result["target"], "new")
