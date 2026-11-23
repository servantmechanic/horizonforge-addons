import base64
import io
import zipfile
from datetime import date

from freezegun import freeze_time

from odoo import Command
from odoo.exceptions import AccessError
from odoo.tests import tagged

from odoo.addons.horizonforge_school_gradebook.tests.common import GradebookCase


@tagged("post_install", "-at_install")
class TestPlanner(GradebookCase):
    """Pacing guides laid over the calendar, progress, the gradebook's
    next column, Fill ahead, export and import, the weekly plan."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.year.day_off_ids.unlink()  # the holidays are shown only anyway
        Item = cls.env["school.pacing.item"]
        rows = [
            ("Lesson 1", cls.homework, 1), ("Lesson 2", cls.homework, 1), ("Lesson 3", cls.homework, 1),
            ("Review", False, 1), ("Test 1", cls.test, 2), ("Lesson 4", cls.homework, 1),
            ("Lesson 5", cls.homework, 1),
        ]
        cls.items = Item.create([
            {"course_id": cls.math_5.id, "sequence": index * 10, "name": name,
             "category_id": category.id if category else False, "days": days}
            for index, (name, category, days) in enumerate(rows, start=1)
        ])
        cls.l1, cls.l2, cls.l3, cls.review, cls.test1, cls.l4, cls.l5 = cls.items

    def _dates(self, section=None):
        section = section or self.section_5
        section._replan()
        return {line.name: line.date for line in section.plan_line_ids}

    def test_plan_from_the_year_start(self):
        # The year starts on Monday 2030-08-26; the test takes Friday and Monday.
        dates = self._dates()
        self.assertEqual(dates["Lesson 1"], date(2030, 8, 26))
        self.assertEqual(dates["Review"], date(2030, 8, 29))
        self.assertEqual(dates["Test 1"], date(2030, 8, 30))
        test_line = self.section_5.plan_line_ids.filtered(lambda l: l.item_id == self.test1)
        self.assertEqual(test_line.date_end, date(2030, 9, 2))
        self.assertEqual(dates["Lesson 4"], date(2030, 9, 3))
        self.assertFalse(any(self.section_5.plan_line_ids.mapped("done")))

    def test_same_day_items(self):
        """Days 0: taken the same day as the item before."""
        self.test1.days = 0
        dates = self._dates()
        self.assertEqual(dates["Test 1"], dates["Review"])
        self.assertEqual(dates["Lesson 4"], date(2030, 8, 30))

    def test_meeting_days_and_no_lessons(self):
        self.env["school.pacing.guide"].create({
            "course_id": self.math_5.id, "meets_tuesday": False, "meets_thursday": False,
        })
        dates = self._dates()
        self.assertEqual([dates[n] for n in ("Lesson 1", "Lesson 2", "Lesson 3")],
                         [date(2030, 8, 26), date(2030, 8, 28), date(2030, 8, 30)])
        # A grade 5 field trip on Wednesday: no lesson that day, for grade 5 only.
        Day = self.env["school.calendar.day"]
        Day.create({
            "year_id": self.year.id, "name": "Zoo trip", "date_start": "2030-08-28", "day_type": "info",
            "no_lessons": True, "audience": "grade_level", "grade_level_ids": [Command.set(self.level_5.ids)],
        })
        Day.create({
            "year_id": self.year.id, "name": "Grade 6 trip", "date_start": "2030-08-30", "day_type": "info",
            "no_lessons": True, "audience": "grade_level", "grade_level_ids": [Command.set(self.level_6.ids)],
        })
        dates = self._dates()
        self.assertEqual(dates["Lesson 2"], date(2030, 8, 30))
        # A day off moves the plan too.
        Day.create({"year_id": self.year.id, "name": "Storm", "date_start": "2030-08-30"})
        self.assertEqual(self._dates()["Lesson 2"], date(2030, 9, 2))

    @freeze_time("2030-09-04")
    def test_taught_items_and_progress(self):
        # Wednesday 9/4: Lessons 1 and 2 were taught (columns with scores).
        for item, day in ((self.l1, "2030-08-26"), (self.l2, "2030-08-27")):
            column = self._assignment(name=item.name, date=day, pacing_item_id=item.id)
            self._score(column, self.anna, 90)
        dates = self._dates()
        self.assertEqual(dates["Lesson 2"], date(2030, 8, 27))
        # The rest follow from today: the class is behind.
        self.assertEqual(dates["Lesson 3"], date(2030, 9, 4))
        self.assertEqual(dates["Test 1"], date(2030, 9, 6))
        lines = {line.name: line for line in self.section_5.plan_line_ids}
        self.assertTrue(lines["Lesson 2"].done)
        self.assertFalse(lines["Lesson 3"].done)
        # By Tuesday 9/3, 7 class days: Lessons 1-3, Review, Test 1 (2 days), Lesson 4 = 6 items due.
        progress = self.section_5._planner_progress()
        self.assertEqual((progress["taught"], progress["count"], progress["behind"]), (2, 7, 4))
        self.assertEqual(self.section_5.planner_progress, "Lesson 2 of 7 · 4 behind")
        # A later item taught: the ones before it count as taught.
        column = self._assignment(name="Lesson 4", date="2030-09-03", pacing_item_id=self.l4.id)
        self._score(column, self.anna, 80)
        self._dates()
        self.assertTrue(all(self.section_5.plan_line_ids.filtered(lambda l: l.sequence <= 6).mapped("done")))

    def test_date_set_by_hand(self):
        self._dates()
        line = self.section_5.plan_line_ids.filtered(lambda l: l.item_id == self.l4)
        line.with_user(self.teacher).date = "2030-09-12"
        self.assertTrue(line.pinned)
        dates = self._dates()
        self.assertEqual(dates["Lesson 4"], date(2030, 9, 12))
        self.assertEqual(dates["Lesson 5"], date(2030, 9, 13))
        line.action_unpin()
        self.assertEqual(self._dates()["Lesson 4"], date(2030, 9, 3))

    def test_columns_of_the_same_name_are_linked(self):
        """A guide started mid-year finds the columns made before it."""
        column = self._assignment(name="Lesson 1", date="2030-08-26")
        self._score(column, self.anna, 90)
        self._dates()
        self.assertEqual(column.pacing_item_id, self.l1)

    def test_gradebook_takes_the_next_item(self):
        section = self.env["school.section"].with_user(self.teacher).browse(self.section_5.id)
        first = self.env["school.assignment"].browse(section.gradebook_add_assignment(self.semester_1.id))
        self.assertEqual((first.name, first.pacing_item_id), ("Lesson 1", self.l1))
        self._score(first, self.anna, 90)
        second = self.env["school.assignment"].browse(section.gradebook_add_assignment(self.semester_1.id, first.id))
        self.assertEqual(second.name, "Lesson 2")
        # The test key: the next test of the guide, whatever comes first.
        third = self.env["school.assignment"].browse(
            section.gradebook_add_assignment(self.semester_1.id, second.id, self.test.id)
        )
        self.assertEqual((third.name, third.pacing_item_id), ("Test 1", self.test1))
        # A column made as a lesson that becomes a test: the next test.
        third.unlink()
        self.assertEqual(section.gradebook_set_category(second.id, self.test.id), "Test 1")
        self.assertEqual(second.pacing_item_id, self.test1)
        # The grid shows the class's progress.
        self.assertIn("of 7", section.gradebook_open(self.section_5.id, self.semester_1.id)["status_note"])

    @freeze_time("2030-08-26")
    def test_fill_ahead(self):
        section = self.env["school.section"].with_user(self.teacher).browse(self.section_5.id)
        self.assertIn("pacing guide", section.gradebook_open(self.section_5.id)["fill_hint"])
        result = section.gradebook_generate(self.semester_1.id)
        # The first week: Lesson 1 to 3 and the test (the review has no grade).
        self.assertEqual(result["count"], 4)
        names = self.section_5.assignment_ids.sorted("date").mapped("name")
        self.assertEqual(names, ["Lesson 1", "Lesson 2", "Lesson 3", "Test 1"])
        test_column = self.section_5.assignment_ids.filtered(lambda a: a.name == "Test 1")
        self.assertEqual(test_column.date, date(2030, 8, 30))
        # Columns made ahead aren't taught yet, and nothing is made twice.
        self.assertFalse(self.section_5.plan_line_ids.filtered(lambda l: l.item_id == self.test1).done)
        self.assertEqual(section.gradebook_generate(self.semester_1.id)["count"], 0)

    def test_export_and_import(self):
        self.l1.write({
            "topic": "Place value", "note": "Pages 1-4",
            "attachment_ids": [Command.create({"name": "sheet.pdf", "raw": b"%PDF sheet"})],
        })
        Transfer = self.env["school.pacing.transfer"]
        action = Transfer.create({"course_id": self.math_5.id}).action_export()
        exported = self.env["ir.attachment"].browse(int(action["url"].split("/")[3].split("?")[0]))
        self.assertTrue(exported.name.endswith(".zip"))
        with zipfile.ZipFile(io.BytesIO(exported.raw)) as archive:
            self.assertIn("files/0010-1-sheet.pdf", archive.namelist())
        Transfer.create({
            "course_id": self.math_6.id, "mode": "import", "data_file": exported.datas, "file_name": exported.name,
        }).action_import()
        copied = self.math_6.pacing_item_ids.sorted("sequence")
        self.assertEqual(copied.mapped("name"), self.items.mapped("name"))
        self.assertEqual((copied[0].topic, copied[0].note), ("Place value", "Pages 1-4"))
        self.assertEqual(copied[0].attachment_ids.raw, b"%PDF sheet")
        self.assertEqual(copied[4].days, 2)
        self.assertFalse(copied[3].category_id)
        # A plain CSV: only Name is needed; replace starts over.
        csv_data = base64.b64encode(b"Name,Category,Days\nLesson A,L,\nTest A,T,2\n")
        Transfer.create({
            "course_id": self.math_6.id, "mode": "import", "data_file": csv_data, "replace": True,
        }).action_import()
        self.assertEqual(self.math_6.pacing_item_ids.mapped("name"), ["Lesson A", "Test A"])

    def test_duplicate_course_copies_guide(self):
        self.env["school.pacing.guide"].create({"course_id": self.math_5.id, "lesson_count": 7})
        copy = self.math_5.copy()
        self.assertEqual(copy.pacing_item_ids.mapped("name"), self.items.mapped("name"))
        self.assertEqual(copy.pacing_guide_id.lesson_count, 7)

    def test_weekly_plan(self):
        self.section_5._replan()
        line = self.section_5.plan_line_ids.filtered(lambda l: l.item_id == self.l2)
        line.note = "Bring rulers"
        self.env["school.calendar.day"].create({
            "year_id": self.year.id, "name": "Picture day", "date_start": "2030-08-28", "day_type": "info",
        })
        wizard = self.env["school.weekly.plan"].with_user(self.teacher).create({"week_date": "2030-08-28"})
        page, = wizard._get_pages()
        self.assertEqual(page["monday"], date(2030, 8, 26))
        self.assertEqual(page["days"][2]["entries"][0]["name"], "Picture day")
        row, = page["rows"]
        self.assertEqual([[item["name"] for item in cell] for cell in row["cells"]],
                         [["Lesson 1"], ["Lesson 2"], ["Lesson 3"], ["Review"], ["Test 1"]])
        self.assertEqual(row["cells"][1][0]["note"], "Bring rulers")
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_school_planner.report_weekly_plan", wizard.ids
        )[0].decode()
        self.assertIn("Bring rulers", html)
        self.assertEqual(wizard.action_print()["report_name"], "horizonforge_school_planner.report_weekly_plan")

    def test_access(self):
        Item = self.env["school.pacing.item"]
        # Every teacher reads every guide; only the course's teachers change it.
        self.assertTrue(Item.with_user(self.other_teacher).search([("course_id", "=", self.math_5.id)]))
        with self.assertRaises(AccessError):
            self.l1.with_user(self.other_teacher).name = "Changed"
        self.l1.with_user(self.teacher).name = "Lesson One"
        Item.with_user(self.other_teacher).create({"course_id": self.math_6.id, "name": "Lesson 1"})
        # Plans stay with the class's teachers.
        self.section_5._replan()
        line = self.section_5.plan_line_ids[:1]
        with self.assertRaises(AccessError):
            line.with_user(self.other_teacher).read(["date"])
        action = self.env["school.plan.line"].with_user(self.teacher).action_open_planner()
        self.assertEqual(action["context"]["search_default_my_classes"], 1)

    def test_screens_load(self):
        for model, kinds in (
            ("school.plan.line", ["calendar", "list", "form", "search"]),
            ("school.pacing.item", ["list", "form", "search"]),
            ("school.pacing.guide", ["list", "form", "search"]),
            ("school.pacing.transfer", ["form"]),
            ("school.weekly.plan", ["form"]),
            ("school.course", ["list"]),
            ("school.calendar.day", ["form", "list"]),
            ("school.section", ["list"]),
        ):
            views = self.env[model].with_user(self.teacher).get_views([(False, kind) for kind in kinds])
            self.assertEqual(set(views["views"]), set(kinds), model)
        self.assertTrue(self.section_5.with_user(self.teacher).read(["planner_progress"]))

    @freeze_time("2030-08-26")
    def test_fill_ahead_many_classes_and_menus(self):
        """Fill Ahead (the menu): a guide's class from the plan, a schedule's
        class from the schedule; both in the Planner menu."""
        self.env["school.assignment.template"].create({
            "course_id": self.math_6.id, "name": "Drill", "category_id": self.homework.id, "monday": True,
        })
        wizard = self.env["school.assignment.generate"].create({"period_id": self.semester_1.id})
        self.assertEqual(wizard.section_ids, self.section_5 | self.section_6)
        wizard.action_generate()
        self.assertEqual(self.section_5.assignment_ids.mapped("pacing_item_id"),
                         self.l1 | self.l2 | self.l3 | self.test1)
        # Math 6 from its schedule: every Monday of the period, numbered.
        drills = self.section_6.assignment_ids
        self.assertTrue(drills)
        self.assertTrue(all(name.startswith("Drill ") for name in drills.mapped("name")))
        self.assertFalse(drills.pacing_item_id)
        planner = self.env.ref("horizonforge_school_planner.menu_school_planner_root")
        for xmlid in ("menu_school_assignment_templates", "menu_school_assignment_generate"):
            self.assertEqual(self.env.ref(f"horizonforge_school_gradebook.{xmlid}").parent_id, planner)


    def test_my_courses(self):
        domain = [("course_id.section_ids", "any", [
            ("year_id.is_current", "=", True), "|",
            ("teacher_id", "=", self.other_teacher.id), ("co_teacher_ids", "in", self.other_teacher.id),
        ])]
        self.env["school.pacing.item"].create({"course_id": self.math_6.id, "name": "Lesson 1"})
        mine = self.env["school.pacing.item"].with_user(self.other_teacher).search(domain)
        self.assertEqual(mine.course_id, self.math_6)
        server_action = self.env.ref("horizonforge_school_planner.school_pacing_guide_server_action")
        action = server_action.with_user(self.other_teacher).run()
        self.assertEqual(action["context"]["search_default_my_courses"], 1)
        self.assertNotIn("search_default_my_courses", server_action.with_user(self.office).run()["context"])

    def _guide(self, **vals):
        return self.env["school.pacing.guide"].with_user(self.other_teacher).create(dict(
            {"course_id": self.math_6.id, "finish": "date", "finish_date": "2030-09-13"}, **vals,
        ))

    def test_build_guide(self):
        """12 lessons, chapters of 5 with a review and a test, in the 15
        class days to Friday 9/13: 18 days needed, nothing doubled up by
        itself; the summary says 3 won't fit."""
        guide = self._guide(lesson_count=12, chapter_size=5, test_after_chapter=True, review_before_test=True)
        guide.action_build()
        items = self.math_6.pacing_item_ids.sorted("sequence")
        self.assertEqual(items.mapped("name")[:7],
                         ["Lesson 1", "Lesson 2", "Lesson 3", "Lesson 4", "Lesson 5", "Review 1", "Test 1"])
        self.assertEqual(items[-1].name, "Test 3", "the last chapter is short")
        self.assertEqual(items.filtered(lambda i: i.name == "Test 2").unit, "Chapter 2")
        self.assertEqual(items.filtered(lambda i: i.name == "Test 2").category_id, self.test)
        self.assertFalse(items.filtered(lambda i: i.name == "Review 2").category_id)
        self.assertEqual(items.mapped("days"), [1] * 18)
        self.assertEqual(guide.summary, "Needs 18 class days, 15 to 09/13/2030: 3 won't fit · "
                                        "double up 3 (Days 0) or finish later · 18 items")
        # The plan runs three class days past the finish date.
        self.assertEqual(max(self.section_6.plan_line_ids.mapped("date")), date(2030, 9, 18))
        # Two lessons doubled up by hand: one still to go.
        items.filtered(lambda i: i.name in ("Lesson 2", "Lesson 4")).days = 0
        guide.invalidate_recordset(["summary"])
        self.assertIn("1 won't fit", guide.summary)
        self.assertIn("2 on the same day as the one before", guide.summary)

    def test_rebuild_keeps_work(self):
        guide = self._guide(lesson_count=4)
        guide.action_build()
        lesson_2 = self.math_6.pacing_item_ids.filtered(lambda i: i.name == "Lesson 2")
        lesson_2.note = "Bring the blocks"
        extra = self.env["school.pacing.item"].create({
            "course_id": self.math_6.id, "name": "Pop quiz", "sequence": 25, "category_id": self.test.id,
        })
        linked = self.math_6.pacing_item_ids.filtered(lambda i: i.name == "Lesson 4")
        self._assignment(section=self.section_6, name="Lesson 4", date="2030-08-29", pacing_item_id=linked.id)
        guide.lesson_count = 2
        guide.action_build()
        names = self.math_6.pacing_item_ids.sorted("sequence").mapped("name")
        # Lesson 3 goes; Lesson 4 has a gradebook column, so it stays; the
        # item added by hand stays in its place.
        self.assertEqual(names, ["Lesson 1", "Lesson 2", "Pop quiz", "Lesson 4"])
        self.assertEqual(lesson_2.note, "Bring the blocks")
        self.assertTrue(extra.exists())

    def test_spread_pace(self):
        guide = self._guide(lesson_count=5, pace="spread")
        guide.action_build()
        self.assertEqual(self.math_6.pacing_item_ids.mapped("days"), [3, 3, 3, 3, 3])
        guide.write({"pace": "daily"})
        guide.action_build()
        self.assertEqual(self.math_6.pacing_item_ids.mapped("days"), [1, 1, 1, 1, 1])
        self.assertEqual(guide.summary, "Needs 5 of the 15 class days to 09/13/2030: 10 spare · 5 items")

    def test_class_order(self):
        """Each day's classes in the order of their guides."""
        self.section_6.teacher_id = self.teacher
        self.env["school.pacing.item"].create({"course_id": self.math_6.id, "name": "Lesson 1"})
        math_5 = self.env["school.pacing.guide"].create({"course_id": self.math_5.id, "sequence": 20})
        math_6 = self.env["school.pacing.guide"].create({"course_id": self.math_6.id, "sequence": 10})
        (self.section_5 | self.section_6)._replan()
        first_day = self.env["school.plan.line"].search([
            ("section_id", "in", (self.section_5 | self.section_6).ids), ("date", "=", "2030-08-26"),
        ], order="class_order, sequence")
        self.assertEqual(first_day.section_id.mapped("course_id"), self.math_6 | self.math_5)
        self.assertEqual(first_day[0].section_id, self.section_6)
        page, = self.env["school.weekly.plan"].with_user(self.teacher).create({"week_date": "2030-08-26"})._get_pages()
        self.assertEqual([row["section"] for row in page["rows"]], [self.section_6, self.section_5])
        # Dragged the other way: the order follows.
        math_6.sequence = 30
        self.assertEqual(first_day.sorted("class_order")[0].section_id, self.section_5)
        self.assertEqual(math_5.sequence, 20)

    def test_open_guide_from_course(self):
        action = self.math_6.with_user(self.other_teacher).action_open_pacing_guide()
        guide = self.env["school.pacing.guide"].browse(action["res_id"])
        self.assertEqual(guide.course_id, self.math_6)
        self.assertEqual(self.math_6.action_open_pacing_guide()["res_id"], guide.id, "made once")
        self.assertEqual(guide.action_open_items()["domain"], [("course_id", "=", self.math_6.id)])
        self.assertEqual(self.env["school.plan.line"].action_weekly_plan()["res_model"], "school.weekly.plan")
