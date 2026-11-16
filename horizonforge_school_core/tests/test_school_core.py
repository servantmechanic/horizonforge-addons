from psycopg2 import IntegrityError

from odoo import Command, fields
from odoo.exceptions import ValidationError
from odoo.tests import tagged
from odoo.tools import mute_logger

from .common import SchoolCoreCase


@tagged("post_install", "-at_install")
class TestSchoolCore(SchoolCoreCase):

    # School years and grading periods

    def test_one_current_year(self):
        other = self.env["school.year"].create({
            "name": "Test 2031-32",
            "date_start": "2031-08-25",
            "date_end": "2032-05-21",
        })
        self.assertEqual(self.env["school.year"]._get_current(), self.year)
        other.action_set_current()
        self.assertTrue(other.is_current)
        self.assertFalse(self.year.is_current)
        self.assertEqual(self.env["school.year"]._get_current(), other)

    def test_year_dates_ordered(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env["school.year"].create({
                "name": "Backwards",
                "date_start": "2031-05-21",
                "date_end": "2030-08-25",
            })

    def test_period_inside_year(self):
        with self.assertRaises(ValidationError):
            self.year.period_ids[0].date_start = "2030-08-01"
        with self.assertRaises(ValidationError):
            self.year.date_end = "2031-03-01"

    def test_period_no_overlap(self):
        with self.assertRaises(ValidationError):
            self.year.period_ids[1].date_start = "2031-01-10"

    def test_period_for_date(self):
        period = self.env["school.period"]._get_for_date(fields.Date.to_date("2031-02-03"))
        self.assertEqual(period, self.year.period_ids[1])
        self.assertFalse(self.env["school.period"]._get_for_date(fields.Date.to_date("2031-01-11")))

    def test_period_display_name(self):
        period = self.year.period_ids[0]
        self.assertEqual(period.display_name, "Test 2030-31 Semester 1")
        self.assertEqual(
            period.with_context(school_period_short_name=True).display_name, "Semester 1"
        )

    def test_settings_current_year(self):
        other = self.env["school.year"].create({
            "name": "Test 2031-32",
            "date_start": "2031-08-25",
            "date_end": "2032-05-21",
        })
        settings = self.env["res.config.settings"].create({})
        self.assertEqual(settings.school_current_year_id, self.year)
        settings.school_current_year_id = other
        settings.school_principal_name = "Dr. Example"
        settings.execute()
        self.assertEqual(self.env["school.year"]._get_current(), other)
        self.assertEqual(self.env.company.school_principal_name, "Dr. Example")

    # Students and patrons

    def test_student_contact(self):
        partner = self.anna.partner_id
        self.assertEqual(partner.name, "Anna Example")
        self.assertEqual(self.anna.display_name, "Example, Anna")
        self.anna.last_name = "Sample"
        self.assertEqual(partner.name, "Anna Sample")
        self.anna.write({"street": "1 Test Road", "phone": "555-0100"})
        self.assertEqual(partner.street, "1 Test Road")

    def test_student_order_and_search(self):
        students = self.env["school.student"].search([("id", "in", (self.anna | self.ben | self.carl).ids)])
        self.assertEqual(students.mapped("first_name"), ["Anna", "Ben", "Carl"])
        found = self.env["school.student"].name_search("T-2")
        self.assertEqual([res[0] for res in found], self.ben.ids)

    def test_student_code_unique(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env["school.student"].create({
                "first_name": "Dup", "last_name": "Code", "student_code": "T-1",
            })

    def test_student_blank_codes_allowed(self):
        students = self.env["school.student"].create([
            {"first_name": "No", "last_name": "Code", "student_code": ""},
            {"first_name": "Also No", "last_name": "Code", "student_code": ""},
        ])
        self.assertEqual(students.mapped("student_code"), [False, False])

    def test_student_archive_keeps_contact(self):
        self.anna.action_archive()
        self.assertFalse(self.anna.active)
        self.assertTrue(self.anna.partner_id.active)
        self.assertNotIn(self.anna, self.env["school.student"].search([]))

    def test_student_copy_gets_own_contact(self):
        twin = self.carl.copy({"first_name": "Cody"})
        self.assertNotEqual(twin.partner_id, self.carl.partner_id)
        self.assertEqual(twin.partner_id.name, "Cody Sample")

    def test_patron_link(self):
        self.assertEqual(self.patron.student_ids, self.anna)
        aunt = self.env["res.partner"].create({"name": "Aunt Example"})
        self.ben.patron_ids = [Command.link(aunt.id)]
        self.assertTrue(aunt.is_patron)
        self.assertEqual(aunt.student_ids, self.ben)

    def test_student_import_template(self):
        template = self.env["school.student"].get_import_templates()[0]["template"]
        self.assertTrue(template.endswith("students_import_template.csv"))

    # Classes and enrollments

    def test_section_defaults(self):
        self.assertEqual(self.section_5.year_id, self.year)
        self.assertEqual(self.section_5.display_name, "Test Math 5 (Test 2030-31)")
        self.section_5.name = "A"
        self.assertEqual(self.section_5.display_name, "Test Math 5 A (Test 2030-31)")

    def test_teacher_domain(self):
        teachers = self.env["res.users"].search(self.env["school.section"]._teacher_domain())
        self.assertIn(self.teacher, teachers)
        self.assertIn(self.admin, teachers)
        self.assertNotIn(self.env.ref("base.public_user"), teachers)

    def test_enroll_grade_levels(self):
        self.section_5.action_enroll_grade_levels()
        self.assertEqual(self.section_5.enrollment_ids.student_id, self.anna | self.ben)
        self.assertEqual(self.section_5.student_count, 2)
        self.assertEqual(
            set(self.section_5.enrollment_ids.mapped("date_start")), {self.year.date_start}
        )
        # Running it again adds nobody twice.
        self.section_5.action_enroll_grade_levels()
        self.assertEqual(len(self.section_5.enrollment_ids), 2)

    def test_enrollment_no_overlap(self):
        enrollment = self.env["school.enrollment"].create({
            "section_id": self.section_5.id,
            "student_id": self.anna.id,
        })
        with self.assertRaises(ValidationError):
            self.env["school.enrollment"].create({
                "section_id": self.section_5.id,
                "student_id": self.anna.id,
                "date_start": "2031-02-01",
            })
        # A student who left can come back later in the year.
        enrollment.date_end = "2030-12-20"
        back = self.env["school.enrollment"].create({
            "section_id": self.section_5.id,
            "student_id": self.anna.id,
            "date_start": "2031-02-01",
        })
        self.assertTrue(back._is_active_on(fields.Date.to_date("2031-03-01")))
        self.assertFalse(enrollment._is_active_on(fields.Date.to_date("2031-03-01")))
        self.assertEqual(self.section_5.student_count, 1)

    def test_enrollment_dates_ordered(self):
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.env["school.enrollment"].create({
                "section_id": self.section_5.id,
                "student_id": self.anna.id,
                "date_start": "2031-02-01",
                "date_end": "2031-01-01",
            })

    def test_enrolled_student_not_deleted(self):
        self.env["school.enrollment"].create({
            "section_id": self.section_5.id,
            "student_id": self.anna.id,
        })
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            self.anna.unlink()

    def test_demo_loader(self):
        self.env["school.year"]._load_school_demo()
        year = self.env["school.year"].search([("name", "=", "2026-27")])
        self.assertEqual(len(year.period_ids), 6)
        self.assertEqual(set(year.period_ids[:5].mapped(lambda p: p.date_end.weekday())), {4})
        self.assertEqual(year.period_ids[-1].date_end, year.date_end)
        self.assertEqual(len(year.section_ids), 40)
        self.assertEqual(len(year.section_ids.enrollment_ids.student_id), 60)
        self.assertEqual(len(year.section_ids.teacher_id), 5)
        self.assertEqual(len(year.section_ids.homeroom_id), 5)
        self.assertEqual(set(year.section_ids.mapped("student_count")), {6})
        # Loading twice changes nothing.
        self.env["school.year"]._load_school_demo()
        self.assertEqual(self.env["school.year"].search_count([("name", "=", "2026-27")]), 1)
