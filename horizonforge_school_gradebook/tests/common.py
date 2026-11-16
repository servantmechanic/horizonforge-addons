from odoo.addons.horizonforge_school_core.tests.common import SchoolCoreCase


class GradebookCase(SchoolCoreCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.homework = cls.env.ref("horizonforge_school_gradebook.score_category_homework")
        cls.test = cls.env.ref("horizonforge_school_gradebook.score_category_test")
        cls.env.company.school_entry_mode = "percent"
        cls.semester_1, cls.semester_2 = cls.year.period_ids
        (cls.section_5 | cls.section_6).action_enroll_grade_levels()

    @classmethod
    def _assignment(cls, section=None, **vals):
        return cls.env["school.assignment"].create({
            "section_id": (section or cls.section_5).id,
            "name": "Lesson",
            "date": "2030-09-03",
            "category_id": cls.homework.id,
            **vals,
        })

    @classmethod
    def _score(cls, assignment, student, value=None, **vals):
        if value is not None:
            vals["value_entered"] = value
        return cls.env["school.score"].create({
            "assignment_id": assignment.id,
            "student_id": student.id,
            **vals,
        })
