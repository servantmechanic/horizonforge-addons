from odoo import _, api, fields, models
from odoo.tools import format_date
from odoo.exceptions import UserError

WEEKDAYS = ["meets_monday", "meets_tuesday", "meets_wednesday", "meets_thursday", "meets_friday"]


class SchoolPacingGuide(models.Model):
    """A course's pacing guide, set up in a few numbers: how many lessons,
    chapters with a test after each, and when it should be finished. Build
    Guide makes the items (Lesson 1, Lesson 2, ... Test 1); items added by
    hand stay in place. The guides' order is the order a teacher's classes
    show each day in the planner and on the weekly plan."""

    _name = "school.pacing.guide"
    _description = "Pacing Guide"
    _order = "sequence, id"
    _rec_name = "course_id"

    course_id = fields.Many2one(
        "school.course",
        string="Course",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        default=10,
        help="Order of the classes each day in the planner and on the weekly plan.",
    )
    active = fields.Boolean(default=True)

    # Lessons
    lesson_count = fields.Integer(
        string="Lessons",
        help="How many lessons the curriculum has, for example 160.",
    )
    lesson_name = fields.Char(
        string="Lesson Name",
        default="Lesson",
        required=True,
        help="Lessons are named this and numbered: Lesson 1, Lesson 2...",
    )
    first_number = fields.Integer(
        string="First Number",
        default=1,
        help="The first lesson's number, for a guide that goes on from last year's book.",
    )
    lesson_category_id = fields.Many2one(
        "school.score.category",
        string="Lesson Category",
        default=lambda self: self.env.ref(
            "horizonforge_school_gradebook.score_category_homework", raise_if_not_found=False
        ),
        help="Their gradebook category. Leave empty for lessons without a grade.",
    )

    # Chapters and tests
    chapter_size = fields.Integer(
        string="Lessons per Chapter",
        help="Leave at 0 for no chapters.",
    )
    chapter_name = fields.Char(
        default="Chapter",
        required=True,
    )
    review_before_test = fields.Boolean(
        string="Review Day Before the Test",
        help="A day without a grade before each chapter's test.",
    )
    test_after_chapter = fields.Boolean(
        string="Test After Each Chapter",
    )
    test_name = fields.Char(
        default="Test",
        required=True,
        help="Tests are named this and numbered: Test 1, Test 2...",
    )
    test_category_id = fields.Many2one(
        "school.score.category",
        string="Test Category",
        default=lambda self: self.env.ref(
            "horizonforge_school_gradebook.score_category_test", raise_if_not_found=False
        ),
    )
    test_days = fields.Integer(
        string="Days per Test",
        default=1,
        help="0: taken the same day as the chapter's last lesson; 2 for a long test.",
    )

    # When
    finish = fields.Selection(
        [
            ("year", "End of the school year"),
            ("period", "End of a grading period"),
            ("date", "A date"),
        ],
        string="Finish By",
        default="year",
        required=True,
    )
    finish_period_id = fields.Many2one(
        "school.period",
        string="Grading Period",
        domain="[('year_id.is_current', '=', True)]",
    )
    finish_date = fields.Date(string="Date")
    pace = fields.Selection(
        [
            ("daily", "One a day, spare days at the end"),
            ("spread", "Spread out to finish on the date"),
        ],
        default="daily",
        required=True,
        help="One a day: each lesson takes a class day, spare days at the end. "
        "Spread out: lessons take more days where there is room, to finish on "
        "the date. Lessons are never doubled up by themselves: the summary says "
        "how many won't fit; set their Days to 0 to double them up.",
    )
    meets_monday = fields.Boolean(string="Mon", default=True)
    meets_tuesday = fields.Boolean(string="Tue", default=True)
    meets_wednesday = fields.Boolean(string="Wed", default=True)
    meets_thursday = fields.Boolean(string="Thu", default=True)
    meets_friday = fields.Boolean(string="Fri", default=True)

    item_count = fields.Integer(
        string="Items",
        compute="_compute_summary",
    )
    target_date = fields.Date(
        string="Finish Date",
        compute="_compute_summary",
    )
    summary = fields.Char(
        compute="_compute_summary",
        help="How the guide's items fit the class days up to the finish date.",
    )

    _course_unique = models.Constraint(
        "UNIQUE(course_id)",
        "A course has one pacing guide.",
    )

    # ------------------------------------------------------------------
    # Days
    # ------------------------------------------------------------------

    def _meeting_weekdays(self):
        self.ensure_one()
        return {index for index, name in enumerate(WEEKDAYS) if self[name]}

    def _year(self):
        return self.env["school.year"]._get_current()

    def _target(self):
        """The finish date chosen, in the current school year."""
        self.ensure_one()
        year = self._year()
        if self.finish == "period" and self.finish_period_id:
            return self.finish_period_id.date_end
        if self.finish == "date" and self.finish_date:
            return self.finish_date
        return year.date_end if year else False

    def _class_days(self, date_to=None):
        """The course's class days this school year up to ``date_to``: those
        of its first class (with the calendar's No lessons days), else the
        school days on the meeting weekdays."""
        self.ensure_one()
        year = self._year()
        if not year:
            return []
        section = self.course_id.section_ids.filtered(lambda s: s.year_id == year)[:1]
        if section:
            return section._planner_class_days(date_to=date_to)
        weekdays = self._meeting_weekdays()
        return [day for day in year._get_school_days(date_to=date_to) if day.weekday() in weekdays]

    @api.depends("course_id.pacing_item_ids.days", "finish", "finish_period_id", "finish_date",
                 *WEEKDAYS)
    def _compute_summary(self):
        for guide in self:
            items = guide.course_id.pacing_item_ids
            guide.item_count = len(items)
            guide.target_date = guide._target() if guide.course_id else False
            if not items or not guide.target_date:
                guide.summary = False
                continue
            days = len(guide._class_days(guide.target_date))
            needed = sum(items.mapped("days"))
            doubled = len(items.filtered(lambda i: not i.days))
            finish = format_date(self.env, guide.target_date)
            if needed > days:
                text = _("Needs %(needed)s class days, %(days)s to %(finish)s: %(n)s won't fit · "
                         "double up %(n)s (Days 0) or finish later",
                         needed=needed, days=days, finish=finish, n=needed - days)
            elif needed == days:
                text = _("Needs all %(days)s class days to %(finish)s", days=days, finish=finish)
            else:
                text = _("Needs %(needed)s of the %(days)s class days to %(finish)s: %(n)s spare",
                         needed=needed, days=days, finish=finish, n=days - needed)
            text += " · " + _("%(items)s items", items=len(items))
            if doubled:
                text += ", " + _("%(n)s on the same day as the one before", n=doubled)
            guide.summary = text

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _plan_rows(self):
        """What the settings make, in order: dicts of name, unit, category,
        days (None: to be paced)."""
        self.ensure_one()
        rows = []
        chapter = 0
        for index in range(self.lesson_count):
            if self.chapter_size and index % self.chapter_size == 0:
                chapter += 1
            unit = f"{self.chapter_name} {chapter}" if self.chapter_size else False
            rows.append({
                "name": f"{self.lesson_name} {self.first_number + index}",
                "unit": unit, "category_id": self.lesson_category_id.id, "days": None,
            })
            chapter_end = self.chapter_size and (
                (index + 1) % self.chapter_size == 0 or index + 1 == self.lesson_count
            )
            if chapter_end and self.review_before_test and self.test_after_chapter:
                rows.append({"name": _("Review %(n)s", n=chapter), "unit": unit, "category_id": False, "days": 1})
            if chapter_end and self.test_after_chapter:
                rows.append({
                    "name": f"{self.test_name} {chapter}", "unit": unit,
                    "category_id": self.test_category_id.id, "days": self.test_days,
                })
        return rows

    @api.model
    def _pace(self, count, slots, spread):
        """Days for ``count`` lessons in ``slots`` class days: 1 each, or
        spread evenly over spare days. Never 0: lessons are doubled up by
        hand (the summary says how many need it)."""
        if count <= 0:
            return []
        if not spread or slots <= count:
            return [1] * count
        per = slots / count
        result, done = [], 0
        for index in range(1, count + 1):
            total = round(index * per)
            result.append(max(1, total - done))
            done = total
        return result

    def action_build(self):
        """Make the guide's items from its settings. Items already there of
        the same name keep their notes, files and gradebook columns; items
        made earlier and no longer wanted go (unless a gradebook column uses
        them); items added by hand stay."""
        self.ensure_one()
        if self.lesson_count <= 0:
            raise UserError(_("Say how many lessons the course has first."))
        if self.lesson_count > 2000:
            raise UserError(_("That's a lot of lessons: 2000 at most."))
        if self.chapter_size < 0 or self.test_days < 0:
            raise UserError(_("Lessons per chapter and days per test can't be negative."))
        Item = self.env["school.pacing.item"]
        course = self.course_id
        rows = self._plan_rows()
        existing = {item.name: item for item in course.pacing_item_ids if item.generated}
        manual = course.pacing_item_ids.filtered(lambda i: not i.generated)
        # Pace the lessons over the class days left by the fixed items.
        slots = len(self._class_days(self._target())) - sum(
            row["days"] for row in rows if row["days"] is not None
        ) - sum(manual.mapped("days"))
        paced = iter(self._pace(len([r for r in rows if r["days"] is None]), slots, self.pace == "spread"))
        kept = Item
        for index, row in enumerate(rows, start=1):
            vals = dict(row, sequence=index * 10, generated=True)
            if vals["days"] is None:
                vals["days"] = next(paced)
            item = existing.pop(row["name"], None)
            if item:
                item.write({k: v for k, v in vals.items() if item[k] != v and not (
                    k == "category_id" and item.category_id.id == v)})
            else:
                item = Item.create(dict(vals, course_id=course.id))
            kept |= item
        leftover = Item.browse([item.id for item in existing.values()])
        used = self.env["school.assignment"].sudo().search([("pacing_item_id", "in", leftover.ids)]).pacing_item_id
        (leftover - used).unlink()
        course.section_ids.filtered(lambda s: s.year_id.is_current)._replan()
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "type": "success",
                "message": _("%(count)s items in %(course)s's guide.", count=len(kept | manual), course=course.name),
                "next": {"type": "ir.actions.client", "tag": "soft_reload"},
            },
        }

    # ------------------------------------------------------------------
    # Buttons
    # ------------------------------------------------------------------

    def action_open_items(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_planner.school_pacing_item_action"
        )
        action["domain"] = [("course_id", "=", self.course_id.id)]
        action["context"] = {"default_course_id": self.course_id.id}
        action["name"] = _("Items: %(course)s", course=self.course_id.name)
        return action

    def action_transfer(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "horizonforge_school_planner.school_pacing_transfer_action"
        )
        action["context"] = {"default_course_id": self.course_id.id}
        return action
