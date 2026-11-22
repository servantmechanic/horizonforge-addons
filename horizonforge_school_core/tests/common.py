from datetime import date as date_type

from dateutil.relativedelta import relativedelta
from lxml import etree

from odoo import Command
from odoo.tests import TransactionCase, new_test_user
from odoo.tools.safe_eval import safe_eval


class SchoolCoreCase(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["school.year"].search([]).is_current = False
        cls.year = cls.env["school.year"].create({
            "name": "Test 2030-31",
            "date_start": "2030-08-26",
            "date_end": "2031-05-23",
            "is_current": True,
            "period_ids": [
                Command.create({
                    "name": "Semester 1",
                    "sequence": 1,
                    "date_start": "2030-08-26",
                    "date_end": "2031-01-10",
                }),
                Command.create({
                    "name": "Semester 2",
                    "sequence": 2,
                    "date_start": "2031-01-13",
                    "date_end": "2031-05-23",
                }),
            ],
        })
        cls.level_5 = cls.env["school.grade.level"].create({"name": "Test Grade 5", "sequence": 5})
        cls.level_6 = cls.env["school.grade.level"].create({"name": "Test Grade 6", "sequence": 6})
        cls.teacher = new_test_user(
            cls.env, login="school_teacher",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        cls.other_teacher = new_test_user(
            cls.env, login="school_teacher_2",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        cls.office = new_test_user(
            cls.env, login="school_office",
            groups="base.group_user,horizonforge_school_core.group_school_office",
        )
        cls.admin = new_test_user(
            cls.env, login="school_admin",
            groups="base.group_user,horizonforge_school_core.group_school_admin",
        )
        cls.patron = cls.env["res.partner"].create({"name": "Pat Example", "is_patron": True})
        cls.math_5 = cls.env["school.course"].create({
            "name": "Test Math 5",
            "code": "TMA5",
            "grade_level_ids": [Command.set(cls.level_5.ids)],
        })
        cls.math_6 = cls.env["school.course"].create({
            "name": "Test Math 6",
            "code": "TMA6",
            "grade_level_ids": [Command.set(cls.level_6.ids)],
        })
        cls.anna, cls.ben = cls.env["school.student"].create([
            {
                "first_name": "Anna",
                "last_name": "Example",
                "student_code": "T-1",
                "grade_level_id": cls.level_5.id,
                "patron_ids": [Command.set(cls.patron.ids)],
            },
            {
                "first_name": "Ben",
                "last_name": "Example",
                "student_code": "T-2",
                "grade_level_id": cls.level_5.id,
            },
        ])
        cls.carl = cls.env["school.student"].create({
            "first_name": "Carl",
            "last_name": "Sample",
            "grade_level_id": cls.level_6.id,
        })
        cls.section_5 = cls.env["school.section"].create({
            "course_id": cls.math_5.id,
            "teacher_id": cls.teacher.id,
        })
        cls.section_6 = cls.env["school.section"].create({
            "course_id": cls.math_6.id,
            "teacher_id": cls.other_teacher.id,
        })


def assert_search_filters(case, model):
    """Evaluate each filter domain and group-by of ``model``'s search view
    the way the web client does, and run it."""
    arch = model.get_views([(False, "search")])["views"]["search"]["arch"]
    names = set()
    for node in etree.fromstring(arch).iter("filter"):
        names.add(node.get("name"))
        values = {"context_today": date_type.today, "relativedelta": relativedelta, "uid": model.env.uid}
        if node.get("domain"):
            model.search(safe_eval(node.get("domain"), values))
        if node.get("context"):
            group_by = safe_eval(node.get("context"), values).get("group_by")
            if group_by:
                model._read_group([], [group_by], ["__count"])
    case.assertNotIn("date", names, "Odoo's Date filter offers calendar quarters, not grading periods")
    return names
