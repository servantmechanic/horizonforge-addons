from datetime import date

from odoo.exceptions import UserError
from odoo.tests import tagged

from .common import SchoolCoreCase


@tagged("post_install", "-at_install")
class TestSchoolCalendarPrint(SchoolCoreCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year.day_off_ids.unlink()
        cls.env["school.calendar.day"].create([
            {
                "year_id": cls.year.id,
                "name": "Fall Break",
                "date_start": "2030-10-14",
                "date_end": "2030-10-15",
            },
            {
                "year_id": cls.year.id,
                "name": "Picture Day",
                "date_start": "2030-10-16",
                "day_type": "info",
            },
        ])

    def _cell(self, months, name, day):
        month = next(m for m in months if m["name"] == name)
        return next(c for week in month["weeks"] for c in week if c["day"] == day)

    def test_calendar_months(self):
        months = self.year._get_calendar_months()
        # August 2030 to May 2031
        self.assertEqual(len(months), 10)
        self.assertEqual(months[0]["name"], "August 2030")
        self.assertEqual(months[-1]["name"], "May 2031")
        # Weeks start on Sunday: August 1, 2030 is a Thursday.
        self.assertEqual([c["day"] for c in months[0]["weeks"][0]], ["", "", "", "", 1, 2, 3])
        self.assertTrue(all(len(week) == 7 for m in months for week in m["weeks"]))
        self.assertEqual(self._cell(months, "August 2030", 20)["class"], "o_out")
        self.assertEqual(self._cell(months, "August 2030", 26)["class"], "o_mark")
        self.assertEqual(self._cell(months, "October 2030", 14)["class"], "o_off")
        self.assertEqual(self._cell(months, "October 2030", 16)["class"], "o_info")
        self.assertEqual(self._cell(months, "October 2030", 19)["class"], "o_weekend")
        self.assertEqual(self._cell(months, "October 2030", 17)["class"], "")
        # The end of Semester 1
        self.assertEqual(self._cell(months, "January 2031", 10)["class"], "o_mark")
        # October 2030 has 23 weekdays, two of them off.
        self.assertEqual(months[2]["school_days"], 21)
        self.assertEqual(sum(m["school_days"] for m in months), len(self.year._get_school_days()))

    def test_day_off_wins(self):
        self.env["school.calendar.day"].create({
            "year_id": self.year.id,
            "name": "Shown on a day off",
            "date_start": "2030-10-14",
            "day_type": "info",
        })
        months = self.year._get_calendar_months()
        self.assertEqual(self._cell(months, "October 2030", 14)["class"], "o_off")

    def test_render(self):
        self.env.company.external_report_layout_id = self.env.ref("web.external_layout_standard")
        html = self.env["ir.actions.report"].with_user(self.teacher)._render_qweb_html(
            "horizonforge_school_core.report_school_calendar", self.year.ids
        )[0].decode()
        self.assertIn("School Calendar Test 2030-31", html)
        self.assertIn("Fall Break", html)
        self.assertIn("Picture Day", html)
        self.assertIn("Semester 2", html)
        self.assertIn("October 2030", html)

    def test_print_for_date(self):
        action = self.env["school.year"].with_user(self.office).action_print_calendar_for_date("2030-11-05")
        self.assertEqual(action["report_name"], "horizonforge_school_core.report_school_calendar")
        self.assertEqual(action["context"]["active_ids"], self.year.ids)
        # Summer between years: the current year
        action = self.env["school.year"].action_print_calendar_for_date(date(2031, 7, 1))
        self.assertEqual(action["context"]["active_ids"], self.year.ids)
        self.year.is_current = False
        with self.assertRaises(UserError):
            self.env["school.year"].action_print_calendar_for_date("2035-07-01")

    def test_calendar_view_has_print(self):
        arch = self.env["school.calendar.day"].get_views([(False, "calendar")])["views"]["calendar"]["arch"]
        self.assertIn('js_class="school_calendar"', arch)
