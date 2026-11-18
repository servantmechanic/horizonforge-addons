from odoo.exceptions import AccessError
from odoo.tests import tagged

from .common import SchoolCoreCase


@tagged("post_install", "-at_install")
class TestSchoolSecurity(SchoolCoreCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        (cls.section_5 | cls.section_6).action_enroll_grade_levels()

    def test_teacher_sees_own_classes(self):
        Section = self.env["school.section"].with_user(self.teacher)
        self.assertEqual(Section.search([("year_id", "=", self.year.id)]), self.section_5)
        with self.assertRaises(AccessError):
            self.section_6.with_user(self.teacher).read(["course_id"])

    def test_co_teacher_sees_class(self):
        self.section_6.co_teacher_ids = self.teacher
        Section = self.env["school.section"].with_user(self.teacher)
        self.assertEqual(
            Section.search([("year_id", "=", self.year.id)]), self.section_5 | self.section_6
        )
        Student = self.env["school.student"].with_user(self.teacher)
        self.assertIn(self.carl, Student.search([]))

    def test_teacher_sees_all_students(self):
        """Every teacher reads every student and patron; enrollments stay
        limited to the teacher's own classes."""
        Student = self.env["school.student"].with_user(self.teacher)
        self.assertEqual(Student.search([]), self.anna | self.ben | self.carl)
        self.assertEqual(self.carl.with_user(self.teacher).first_name, "Carl")
        self.assertEqual(self.anna.with_user(self.other_teacher).patron_ids.name, "Pat Example")
        Enrollment = self.env["school.enrollment"].with_user(self.teacher)
        self.assertEqual(Enrollment.search([]).section_id, self.section_5)

    def test_teacher_is_read_only(self):
        with self.assertRaises(AccessError):
            self.section_5.with_user(self.teacher).name = "B"
        with self.assertRaises(AccessError):
            self.anna.with_user(self.teacher).first_name = "Changed"
        with self.assertRaises(AccessError):
            self.section_5.enrollment_ids[0].with_user(self.teacher).unlink()
        with self.assertRaises(AccessError):
            self.year.with_user(self.teacher).name = "Changed"

    def test_office_manages_students_and_enrollments(self):
        Section = self.env["school.section"].with_user(self.office)
        self.assertEqual(
            Section.search([("year_id", "=", self.year.id)]), self.section_5 | self.section_6
        )
        student = self.env["school.student"].with_user(self.office).create({
            "first_name": "Dana",
            "last_name": "Sample",
            "grade_level_id": self.level_6.id,
        })
        self.assertEqual(student.partner_id.name, "Dana Sample")
        self.env["school.enrollment"].with_user(self.office).create({
            "section_id": self.section_6.id,
            "student_id": student.id,
        })
        self.carl.with_user(self.office).first_name = "Carlos"
        with self.assertRaises(AccessError):
            self.section_6.with_user(self.office).teacher_id = self.teacher
        with self.assertRaises(AccessError):
            self.year.with_user(self.office).name = "Changed"
        with self.assertRaises(AccessError):
            student.with_user(self.office).unlink()

    def test_admin_manages_everything(self):
        self.year.with_user(self.admin).period_ids[0].locked = True
        self.section_6.with_user(self.admin).teacher_id = self.teacher
        course = self.env["school.course"].with_user(self.admin).create({"name": "Test Art"})
        section = self.env["school.section"].with_user(self.admin).create({"course_id": course.id})
        section.unlink()
