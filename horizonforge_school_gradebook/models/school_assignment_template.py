from odoo import _, api, fields, models
from odoo.exceptions import ValidationError

from .school_assignment import ENTRY_MODES

WEEKDAY_FIELDS = ["monday", "tuesday", "wednesday", "thursday", "friday"]


class SchoolAssignmentTemplate(models.Model):
    _name = "school.assignment.template"
    _description = "Assignment Schedule"
    _order = "course_id, sequence, id"

    course_id = fields.Many2one(
        "school.course",
        string="Course",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(default=10)
    name = fields.Char(
        string="Assignment Name",
        required=True,
        help="For example Lesson or Spelling Test.",
    )
    category_id = fields.Many2one(
        "school.score.category",
        string="Category",
        required=True,
        ondelete="restrict",
    )
    monday = fields.Boolean(string="Mon")
    tuesday = fields.Boolean(string="Tue")
    wednesday = fields.Boolean(string="Wed")
    thursday = fields.Boolean(string="Thu")
    friday = fields.Boolean(string="Fri")
    numbered = fields.Boolean(
        default=True,
        help="Number the assignments through the year: Lesson 1, Lesson 2 and so on.",
    )
    max_points = fields.Float(
        default=100.0,
        required=True,
    )
    entry_mode = fields.Selection(
        ENTRY_MODES,
        help="Leave empty to use the class's entry mode.",
    )
    active = fields.Boolean(default=True)

    @api.constrains("course_id", *WEEKDAY_FIELDS)
    def _check_weekdays(self):
        for template in self:
            if not template._weekdays():
                raise ValidationError(_(
                    "Pick at least one weekday for %(name)s.", name=template.name
                ))

    def _weekdays(self):
        """Weekday numbers (Monday is 0) the assignment falls on."""
        self.ensure_one()
        return {index for index, name in enumerate(WEEKDAY_FIELDS) if self[name]}
