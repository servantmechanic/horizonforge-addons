from datetime import timedelta

from odoo import Command, fields
from odoo.tests import tagged

from .common import SchoolCoreCase, assert_search_filters


@tagged("post_install", "-at_install")
class TestSchoolLists(SchoolCoreCase):
    """Search filters and the way list screens open."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.context_today(cls.env.user)
        cls.now_year = cls.env["school.year"].create({
            "name": "Test Now",
            "date_start": today - timedelta(days=60),
            "date_end": today + timedelta(days=60),
            "period_ids": [
                Command.create({"name": "Earlier", "sequence": 1,
                                "date_start": today - timedelta(days=60), "date_end": today - timedelta(days=1)}),
                Command.create({"name": "Now", "sequence": 2,
                                "date_start": today, "date_end": today + timedelta(days=60)}),
            ],
        })
        cls.earlier, cls.now = cls.now_year.period_ids

    def test_current_and_previous_period(self):
        Period = self.env["school.period"]
        self.assertEqual(Period._get_current(), self.now)
        self.assertEqual(Period._get_previous(), self.earlier)
        self.assertEqual(Period.search([("is_current", "=", True)]), self.now)
        self.assertEqual(Period.search([("is_previous", "=", True)]), self.earlier)
        self.assertNotIn(self.now, Period.search([("is_current", "=", False)]))
        self.assertTrue(self.now.is_current)
        self.assertFalse(self.earlier.is_current)

    def test_list_action_defaults(self):
        Period = self.env["school.period"]
        xmlid = "horizonforge_school_core.school_enrollment_action"
        context = Period.with_user(self.teacher)._school_list_action(xmlid, "my_classes")["context"]
        self.assertEqual(context["searchpanel_default_period_id"], self.now.id)
        self.assertEqual(context["search_default_my_classes"], 1)
        # Kept from the window action.
        self.assertEqual(context["search_default_current_year"], 1)
        # The office starts on everyone.
        context = Period.with_user(self.office)._school_list_action(xmlid, "my_classes")["context"]
        self.assertNotIn("search_default_my_classes", context)

    def test_search_filters(self):
        assert_search_filters(self, self.env["school.student"].with_user(self.teacher))
        assert_search_filters(self, self.env["school.enrollment"].with_user(self.teacher))
        assert_search_filters(self, self.env["school.section"].with_user(self.teacher))

    def test_my_students(self):
        (self.section_5 | self.section_6).action_enroll_grade_levels()
        Student = self.env["school.student"].with_user(self.teacher)
        mine = Student.search([("enrollment_ids", "any", [
            ("year_id.is_current", "=", True),
            "|", ("section_id.teacher_id", "=", self.teacher.id),
            ("section_id.co_teacher_ids", "in", self.teacher.id)])])
        self.assertIn(self.anna, mine)
        self.assertNotIn(self.carl, mine)
