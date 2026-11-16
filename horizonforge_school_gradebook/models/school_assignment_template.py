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
    week_interval = fields.Integer(
        string="Every (Weeks)",
        default=1,
        required=True,
        help="1 for every week, 2 for every other week, 3 for every third "
        "week and so on. Weeks without school aren't counted.",
    )
    first_week = fields.Integer(
        string="First Week",
        default=1,
        required=True,
        help="The school week of the first one, counted from the start of "
        "the year. A test every 3 weeks that closes each unit starts in week 3.",
    )
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

    _week_interval_positive = models.Constraint(
        "CHECK(week_interval >= 1 AND first_week >= 1)",
        "Every (weeks) and the first week must be 1 or more.",
    )

    def _in_week(self, week_number):
        """Whether the schedule has its assignments in this school week."""
        self.ensure_one()
        return (
            week_number >= self.first_week
            and (week_number - self.first_week) % self.week_interval == 0
        )

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
