from bisect import bisect_right
from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import AccessError

class SchoolCourse(models.Model):
    _inherit = "school.course"

    pacing_item_ids = fields.One2many(
        "school.pacing.item",
        "course_id",
        string="Pacing Guide",
        copy=True,
    )
    pacing_item_count = fields.Integer(
        string="Guide Items",
        compute="_compute_pacing_item_count",
    )
    pacing_guide_id = fields.Many2one(
        "school.pacing.guide",
        string="Pacing Guide Settings",
        compute="_compute_pacing_guide_id",
    )

    def _compute_pacing_item_count(self):
        counts = dict(self.env["school.pacing.item"]._read_group(
            [("course_id", "in", self.ids)], ["course_id"], ["__count"],
        ))
        for course in self:
            course.pacing_item_count = counts.get(course, 0)

    def copy(self, default=None):
        """Math 2 into Math 3: the guide's settings come along with its items."""
        copies = super().copy(default=default)
        for course, copy in zip(self, copies):
            if course.pacing_guide_id:
                course.pacing_guide_id.copy({"course_id": copy.id})
        return copies

    def _compute_pacing_guide_id(self):
        guides = self.env["school.pacing.guide"].with_context(active_test=False).search(
            [("course_id", "in", self.ids)]
        )
        by_course = {guide.course_id: guide for guide in guides}
        for course in self:
            course.pacing_guide_id = by_course.get(course, False)

    def _meeting_weekdays(self):
        """The weekdays the course meets: its guide's, else Monday to Friday."""
        self.ensure_one()
        guide = self.pacing_guide_id
        return guide._meeting_weekdays() if guide else {0, 1, 2, 3, 4}

    def action_open_pacing_guide(self):
        """The course's guide, made the first time."""
        self.ensure_one()
        Guide = self.env["school.pacing.guide"].with_context(active_test=False)
        guide = Guide.search([("course_id", "=", self.id)], limit=1) or Guide.create({"course_id": self.id})
        return {
            "type": "ir.actions.act_window",
            "res_model": "school.pacing.guide",
            "res_id": guide.id,
            "view_mode": "form",
            "target": "current",
            "name": _("Pacing Guide: %(course)s", course=self.name),
        }


class SchoolCalendarDay(models.Model):
    _inherit = "school.calendar.day"

    no_lessons = fields.Boolean(
        string="No Lessons",
        help="School is in session (attendance is taken) but no lesson is "
        "taught, for those the entry is for: a field trip, testing day or "
        "program. Their plans move on a day.",
    )

    @api.onchange("day_type")
    def _onchange_day_type_no_lessons(self):
        if self.day_type == "off":
            self.no_lessons = False

    def _applies_to_section(self, section):
        """Whether the entry is for a class: everyone, its grade levels,
        its homeroom (or its students'), or its teachers."""
        self.ensure_one()
        if self.audience == "all":
            return True
        if self.audience == "grade_level":
            return bool(self.grade_level_ids & section.course_id.grade_level_ids)
        if self.audience == "homeroom":
            homerooms = section.homeroom_id | section.sudo().enrollment_ids.student_id.homeroom_id
            return bool(self.homeroom_ids & homerooms)
        return bool(self.teacher_ids & (section.teacher_id | section.co_teacher_ids))


class SchoolAssignment(models.Model):
    _inherit = "school.assignment"

    pacing_item_id = fields.Many2one(
        "school.pacing.item",
        string="Pacing Guide Item",
        ondelete="set null",
        index=True,
        copy=False,
        help="The guide item this column is for: it counts as taught once it "
        "has scores or its day has passed.",
    )


class SchoolSection(models.Model):
    _inherit = "school.section"

    plan_line_ids = fields.One2many(
        "school.plan.line",
        "section_id",
        string="Plan",
    )
    planner_progress = fields.Char(
        string="Progress",
        compute="_compute_planner_progress",
        help="Through the course's pacing guide: the last item taught, how "
        "many there are, and how far ahead or behind the class is against "
        "the guide started on the year's first day.",
    )

    # ------------------------------------------------------------------
    # Class days
    # ------------------------------------------------------------------

    def _planner_class_days(self, date_from=None, date_to=None):
        """The days the class has a lesson: school days on the course's
        meeting weekdays, without the calendar's No lessons days for it."""
        self.ensure_one()
        year = self.year_id
        weekdays = self.course_id._meeting_weekdays()
        no_lessons = set()
        for entry in year.day_off_ids.filtered(lambda d: d.day_type == "info" and d.no_lessons):
            if entry._applies_to_section(self):
                day = entry.date_start
                while day <= entry.date_end:
                    no_lessons.add(day)
                    day += timedelta(days=1)
        return [
            day for day in year._get_school_days(date_from, date_to)
            if day.weekday() in weekdays and day not in no_lessons
        ]

    # ------------------------------------------------------------------
    # The plan
    # ------------------------------------------------------------------

    def _planner_taught(self, items, assignments):
        """Index of the last item taught, -1 for none. An item is taught
        once its gradebook column has scores or its day has passed; the
        items before it then count as taught too."""
        today = fields.Date.context_today(self)
        last = -1
        for index, item in enumerate(items):
            assignment = assignments.get(item.id)
            if assignment and (assignment.date <= today or assignment.score_ids):
                last = index
        return last

    def _planner_link_assignments(self, items, save=True):
        """``{item id: assignment}``: the columns made for the guide's
        items, and columns of the same name made before the guide (linked
        when ``save``, so a guide can start mid-year)."""
        Assignment = self.env["school.assignment"].sudo()
        linked = Assignment.search([("section_id", "=", self.id), ("pacing_item_id", "in", items.ids)])
        result = {}
        for assignment in linked.sorted(lambda a: (a.date, a.sequence, a.id)):
            result.setdefault(assignment.pacing_item_id.id, assignment)
        loose = Assignment.search([("section_id", "=", self.id), ("pacing_item_id", "=", False)])
        by_name = {}
        for assignment in loose.sorted(lambda a: (a.date, a.sequence, a.id)):
            by_name.setdefault((assignment.name or "").strip().lower(), assignment)
        for item in items:
            if item.id in result or not item.category_id:
                continue
            assignment = by_name.pop((item.name or "").strip().lower(), None)
            if assignment:
                if save:
                    # sudo: a link only; a locked period stays as it is.
                    assignment.pacing_item_id = item
                result[item.id] = assignment
        return result

    def _replan(self):
        """Lay each class's pacing guide over its class days. Taught items
        keep the day they were taught; the rest follow from the next class
        day. A date set by hand or a column made ahead holds, and the
        items after it follow it."""
        today = fields.Date.context_today(self)
        Line = self.env["school.plan.line"].sudo().with_context(school_replanning=True)
        for section in self:
            items = section.course_id.pacing_item_ids.sorted(lambda i: (i.sequence, i.id))
            existing = {line.item_id.id: line for line in Line.search([("section_id", "=", section.id)])}
            stale = Line.browse([line.id for item_id, line in existing.items() if item_id not in items.ids])
            stale.unlink()
            if not items or not section.year_id:
                continue
            assignments = section._planner_link_assignments(items)
            taught = section._planner_taught(items, assignments)
            last_date = None
            for index in range(taught + 1):
                assignment = assignments.get(items[index].id)
                if assignment:
                    last_date = max(last_date, assignment.date) if last_date else assignment.date
            start = max(today, section.year_id.date_start)
            if last_date and last_date >= start:
                start = last_date + timedelta(days=1)
            days = section._planner_class_days(start)
            cursor = 0
            previous = None
            values = {}
            for index, item in enumerate(items):
                line = existing.get(item.id)
                assignment = assignments.get(item.id)
                if index <= taught:
                    date = assignment.date if assignment else previous
                    values[item] = {"date": date, "date_end": date, "done": True}
                    previous = date or previous
                    continue
                span = max(item.days, 1)
                if assignment or (line and line.pinned and line.date):
                    # A column made ahead, or a date set by hand: it holds,
                    # and what comes after follows it.
                    date = assignment.date if assignment else line.date
                    after = bisect_right(days, date)
                    end = days[after + span - 2] if span > 1 and after + span - 2 < len(days) else date
                    cursor = max(cursor, after + span - 1)
                elif not item.days and previous:
                    # Taken the same day as the item before (a test on a lesson day).
                    date = end = previous
                else:
                    date = days[cursor] if cursor < len(days) else False
                    end = days[cursor + span - 1] if cursor + span - 1 < len(days) else date
                    cursor += span
                previous = date or previous
                values[item] = {"date": date, "date_end": max(end, date) if end and date else date, "done": False}
            for sequence, item in enumerate(items, start=1):
                assignment = assignments.get(item.id)
                vals = dict(
                    values[item], sequence=sequence, assignment_id=assignment.id if assignment else False,
                    guide_id=section.course_id.pacing_guide_id.id,
                )
                line = existing.get(item.id)
                if line:
                    current = {
                        "date": line.date, "date_end": line.date_end, "done": line.done,
                        "sequence": line.sequence, "assignment_id": line.assignment_id.id,
                        "guide_id": line.guide_id.id,
                    }
                    changed = {key: value for key, value in vals.items() if current[key] != value}
                    if changed:
                        line.write(changed)
                else:
                    Line.create(dict(vals, section_id=section.id, item_id=item.id))

    # ------------------------------------------------------------------
    # Progress
    # ------------------------------------------------------------------

    def _planner_progress(self):
        """``{"taught", "count", "last", "behind", "short"}`` for a class
        with a pacing guide, else None. Behind: items due by yesterday,
        had the guide started on the year's first class day, less those
        taught. Short: class days the rest needs beyond the year's end."""
        self.ensure_one()
        items = self.course_id.pacing_item_ids.sorted(lambda i: (i.sequence, i.id))
        if not items or not self.year_id:
            return None
        today = fields.Date.context_today(self)
        assignments = self._planner_link_assignments(items, save=False)
        taught = self._planner_taught(items, assignments)
        days = self._planner_class_days()
        past = len([day for day in days if day < today])
        due, used = 0, 0
        for item in items:
            if used >= past:
                break
            used += item.days
            due += 1
        remaining = sum(item.days for item in items[taught + 1:])
        left = len([day for day in days if day >= today])
        return {
            "taught": taught + 1,
            "count": len(items),
            "last": items[taught].name if taught >= 0 else "",
            "behind": due - (taught + 1),
            "short": max(0, remaining - left),
        }

    @api.depends_context("uid")
    def _compute_planner_progress(self):
        for section in self:
            progress = section._planner_progress() if section.id else None
            section.planner_progress = section._planner_progress_text(progress) if progress else False

    @api.model
    def _planner_progress_text(self, progress):
        if progress["taught"]:
            text = _("%(last)s of %(count)s", last=progress["last"], count=progress["count"])
        else:
            text = _("Not started, %(count)s items", count=progress["count"])
        behind = progress["behind"]
        if behind > 0:
            text += " · " + _("%(n)s behind", n=behind)
        elif behind < 0:
            text += " · " + _("%(n)s ahead", n=-behind)
        else:
            text += " · " + _("on pace")
        if progress["short"]:
            text += " · " + _("%(n)s days short of the year", n=progress["short"])
        return text

    # ------------------------------------------------------------------
    # Gradebook
    # ------------------------------------------------------------------

    def _planner_next_item(self, category=None, exclude=None):
        """The next item of the guide that still needs a gradebook column:
        after the last one taught, graded, without a column; of
        ``category`` when given."""
        self.ensure_one()
        items = self.course_id.pacing_item_ids.sorted(lambda i: (i.sequence, i.id))
        if not items:
            return self.env["school.pacing.item"]
        assignments = self._planner_link_assignments(items)
        taught = self._planner_taught(items, assignments)
        for item in items[taught + 1:]:
            if not item.category_id or item.id in assignments or item == exclude:
                continue
            if category and item.category_id != category:
                continue
            return item
        return self.env["school.pacing.item"]

    def _planner_item_vals(self, item, vals):
        return dict(
            vals,
            name=item.name,
            category_id=item.category_id.id,
            max_points=item.max_points or vals.get("max_points") or 100.0,
            entry_mode=item.entry_mode or vals.get("entry_mode") or self._get_entry_mode(),
            pacing_item_id=item.id,
        )

    def _gradebook_next_assignment_vals(self, vals, forced_category=False):
        """With a pacing guide, the next column is the guide's next item
        (of the category asked for, when a key asked for one)."""
        vals = super()._gradebook_next_assignment_vals(vals, forced_category=forced_category)
        category = self.env["school.score.category"].browse(vals["category_id"]) if forced_category else None
        item = self._planner_next_item(category)
        return self._planner_item_vals(item, vals) if item else vals

    def gradebook_set_category(self, assignment_id, category_id):
        """A column made from the guide that changes category becomes the
        guide's next item of that category: Lesson 23 pressed - is Test 3."""
        self.ensure_one()
        assignment = self.env["school.assignment"].browse(assignment_id)
        category = self.env["school.score.category"].browse(category_id)
        if assignment.section_id == self and assignment.pacing_item_id and assignment.category_id != category:
            item = self._planner_next_item(category, exclude=assignment.pacing_item_id)
            if item:
                vals = self._planner_item_vals(item, {
                    "max_points": assignment.max_points, "entry_mode": assignment.entry_mode,
                })
                # The column's typed scores keep their entry mode.
                if assignment.score_ids:
                    vals.pop("entry_mode")
                    vals.pop("max_points")
                assignment.write(vals)
                return assignment.name
            assignment.pacing_item_id = False  # no item of that category left
        return super().gradebook_set_category(assignment_id, category_id)

    def _gradebook_status_note(self):
        progress = self._planner_progress()
        return self._planner_progress_text(progress) if progress else super()._gradebook_status_note()

    def _can_fill_ahead(self):
        return bool(self.course_id.pacing_item_ids) or super()._can_fill_ahead()

    def _fill_ahead(self, period):
        """With a pacing guide: this week's lessons, from the plan."""
        self.ensure_one()
        if self.course_id.pacing_item_ids:
            return self._planner_fill(period)
        return super()._fill_ahead(period)

    def _gradebook_fill_hint(self):
        if self.course_id.pacing_item_ids:
            return _("Create the gradebook columns of this week's lessons from the pacing guide")
        return super()._gradebook_fill_hint()

    def gradebook_generate(self, period_id):
        """Fill ahead with a pacing guide: the columns of the graded items
        planned up to the end of the week, inside the grading period."""
        self.ensure_one()
        if not self.course_id.pacing_item_ids:
            return super().gradebook_generate(period_id)
        period = self.env["school.period"].browse(period_id)
        if not self._gradebook_can_edit(period):
            raise AccessError(_("You can't add assignments to this class for %(period)s.", period=period.name))
        count = len(self._planner_fill(period))
        return {
            "count": count,
            "message": _("%(count)s columns created from the pacing guide, through Friday.", count=count)
            if count else _("Nothing to add: this week's lessons already have their columns."),
        }

    def _planner_fill(self, period):
        """Columns for the graded items planned from the grading period's
        start (or today) to that week's Friday."""
        self.ensure_one()
        self._replan()
        today = fields.Date.context_today(self)
        base = max(today, period.date_start)
        friday = base + timedelta(days=(4 - base.weekday()) % 7)
        end = min(friday, period.date_end)
        lines = self.plan_line_ids.filtered(
            lambda l: not l.assignment_id and l.category_id and l.date
            and period.date_start <= l.date <= end
        )
        Assignment = self.env["school.assignment"]
        vals_list = []
        for line in lines.sorted("sequence"):
            last = Assignment.search([
                ("section_id", "=", self.id), ("category_id", "=", line.category_id.id),
            ], order="date desc, sequence desc, id desc", limit=1)
            vals_list.append(self._planner_item_vals(line.item_id, {
                "section_id": self.id,
                "date": line.date,
                "period_id": period.id,
                "max_points": last.max_points,
                "entry_mode": last.entry_mode,
                "sequence": line.sequence,
            }))
        created = Assignment.create(vals_list)
        self._replan()
        return created
