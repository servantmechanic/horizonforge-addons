from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from odoo.addons.horizonforge_school_gradebook.models.school_assignment import ENTRY_MODES


class SchoolPacingItem(models.Model):
    """One step of a course's pacing guide, in teaching order: a lesson, a
    test, a review day. Built once per curriculum, then laid over each
    year's calendar by the class's plan."""

    _name = "school.pacing.item"
    _description = "Pacing Guide Item"
    _order = "course_id, sequence, id"

    course_id = fields.Many2one(
        "school.course",
        string="Course",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        default=10,
        help="Teaching order.",
    )
    unit = fields.Char(
        help="The section or chapter it belongs to, for example Chapter 3.",
    )
    name = fields.Char(
        required=True,
        help="As the gradebook column is named, for example Lesson 23 or Test 3.",
    )
    topic = fields.Char(
        help="What it covers, for example Adding fractions.",
    )
    category_id = fields.Many2one(
        "school.score.category",
        string="Category",
        ondelete="restrict",
        help="Lesson, test... Leave empty for a day without a grade (a review "
        "day): it is planned, but gets no gradebook column.",
    )
    days = fields.Integer(
        default=1,
        required=True,
        help="Class days it takes, for example 2 for a long test, or 0 when it "
        "is taken the same day as the item before (a quiz on a lesson day).",
    )
    max_points = fields.Float(
        help="Max points of its gradebook column. Leave at 0 for the last "
        "assignment of the category's.",
    )
    entry_mode = fields.Selection(
        ENTRY_MODES,
        help="How its scores are typed. Leave empty for the class's entry mode.",
    )
    note = fields.Text(
        string="Notes",
        help="For the teacher, every year: pages, materials, what to prepare. "
        "Printed on the weekly plan.",
    )
    attachment_ids = fields.Many2many(
        "ir.attachment",
        "school_pacing_item_attachment_rel",
        "item_id",
        "attachment_id",
        string="Files",
        help="Worksheets, the quiz to print, answer keys. They come with the "
        "guide when it is exported.",
    )
    attachment_count = fields.Integer(
        string="Number of Files",
        compute="_compute_attachment_count",
    )
    active = fields.Boolean(default=True)
    generated = fields.Boolean(
        string="From the Settings",
        copy=True,
        help="Made by Build Guide from the guide's settings. Items added by "
        "hand stay when the guide is built again.",
    )

    _days_positive = models.Constraint(
        "CHECK(days >= 0)",
        "An item can't take fewer than 0 class days.",
    )

    @api.depends("attachment_ids")
    def _compute_attachment_count(self):
        for item in self:
            item.attachment_count = len(item.attachment_ids)

    @api.depends("name", "topic")
    def _compute_display_name(self):
        for item in self:
            item.display_name = f"{item.name}: {item.topic}" if item.topic else (item.name or "")

    @api.constrains("max_points")
    def _check_max_points(self):
        for item in self:
            if item.max_points < 0:
                raise ValidationError(_("%(name)s: max points can't be negative.", name=item.name))

    def _link_files(self):
        """Tie uploaded files to the item, so that who may open them follows
        who may see the guide."""
        for item in self:
            loose = item.attachment_ids.sudo().filtered(
                lambda a: a.res_model != self._name or a.res_id != item.id
            )
            loose.write({"res_model": self._name, "res_id": item.id})

    @api.model_create_multi
    def create(self, vals_list):
        items = super().create(vals_list)
        items.filtered("attachment_ids")._link_files()
        return items

    def write(self, vals):
        res = super().write(vals)
        if "attachment_ids" in vals:
            self._link_files()
        return res
