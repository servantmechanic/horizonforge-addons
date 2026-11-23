from odoo import api, fields, models


class SchoolPlanLine(models.Model):
    """A pacing guide item on a class's calendar. Lines are worked out by
    ``school.section._replan()``: taught items stay where they were taught,
    the rest follow on the class's next days. A date the teacher sets by
    hand (or a gradebook column made ahead) holds, and what comes after
    moves along."""

    _name = "school.plan.line"
    _description = "Plan Line"
    _order = "section_id, sequence, id"

    section_id = fields.Many2one(
        "school.section",
        string="Class",
        required=True,
        ondelete="cascade",
        index=True,
    )
    item_id = fields.Many2one(
        "school.pacing.item",
        string="Item",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer()
    guide_id = fields.Many2one(
        "school.pacing.guide",
        string="Pacing Guide",
        ondelete="set null",
    )
    class_order = fields.Integer(
        string="Class Order",
        related="guide_id.sequence",
        store=True,
        help="The order of the teacher's classes each day: their guides' order.",
    )
    course_id = fields.Many2one(related="section_id.course_id", store=True)
    year_id = fields.Many2one(related="section_id.year_id", store=True)
    teacher_id = fields.Many2one(related="section_id.teacher_id", store=True, string="Teacher")
    name = fields.Char(related="item_id.name")
    topic = fields.Char(related="item_id.topic")
    unit = fields.Char(related="item_id.unit")
    category_id = fields.Many2one(related="item_id.category_id")
    item_note = fields.Text(related="item_id.note", string="Guide Notes")
    date = fields.Date(
        help="The class day it is planned for, or taught on. Empty: it no "
        "longer fits in the school year.",
    )
    date_end = fields.Date(
        string="Until",
        help="Its last class day, for an item that takes more than one.",
    )
    done = fields.Boolean(
        string="Completed",
        help="Its gradebook column has scores or its day has passed, or a "
        "later item has been taught.",
    )
    pinned = fields.Boolean(
        string="Date Set by Hand",
        help="The date was set by hand: the plan keeps it, and moves what "
        "comes after. Clear it to let the plan place the item again.",
    )
    note = fields.Text(
        string="Day Note",
        help="The teacher's note for this lesson's day, for example Bring "
        "rulers. Printed on the weekly plan.",
    )
    assignment_id = fields.Many2one(
        "school.assignment",
        string="Gradebook Column",
        ondelete="set null",
    )

    _section_item_unique = models.Constraint(
        "UNIQUE(section_id, item_id)",
        "An item is planned once per class.",
    )

    @api.depends("section_id", "item_id")
    def _compute_display_name(self):
        for line in self:
            label = line.item_id.name or ""
            line.display_name = f"{line.section_id.course_id.name}: {label}" if line.section_id else label

    def write(self, vals):
        """A date changed by hand (in the list, or dragged in the calendar)
        holds; the gradebook column made ahead moves with it."""
        if "date" in vals and not self.env.context.get("school_replanning"):
            vals = dict(vals, pinned=True)
            if "date_end" not in vals and vals["date"]:
                vals["date_end"] = vals["date"]
        res = super().write(vals)
        if "date" in vals and not self.env.context.get("school_replanning"):
            for line in self.filtered(lambda l: l.assignment_id and not l.done and l.date):
                line.assignment_id.date = line.date
            self.section_id._replan()
        return res

    def action_unpin(self):
        """Let the plan place the item again."""
        self.with_context(school_replanning=True).write({"pinned": False})
        self.section_id._replan()
        return True

    @api.model
    def action_weekly_plan(self):
        """The Weekly Plan button above the planner."""
        return self.env["ir.actions.act_window"]._for_xml_id("horizonforge_school_planner.school_weekly_plan_action")

    @api.model
    def action_open_planner(self):
        """School, Planner: the user's classes planned afresh, on a calendar."""
        user = self.env.user
        Section = self.env["school.section"]
        domain = [("year_id.is_current", "=", True), ("course_id.pacing_item_ids", "!=", False)]
        if not user.has_group("horizonforge_school_core.group_school_office"):
            domain += ["|", ("teacher_id", "=", user.id), ("co_teacher_ids", "in", user.id)]
        sections = Section.search(domain)
        sections._replan()
        action = self.env["school.period"]._school_list_action(
            "horizonforge_school_planner.school_plan_line_action", "my_classes"
        )
        # The list shows one class at a time: the user's first.
        mine = sections.filtered(lambda s: user in (s.teacher_id | s.co_teacher_ids))
        if mine:
            action["context"]["searchpanel_default_section_id"] = mine.sorted(
                lambda s: (s.course_id.sequence, s.course_id.name or "", s.id)
            )[0].id
        return action
