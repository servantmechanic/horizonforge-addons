from odoo import fields, models


class SchoolGradingScale(models.Model):
    _name = "school.grading.scale"
    _description = "Grading Scale"
    _order = "name"

    name = fields.Char(required=True)
    line_ids = fields.One2many(
        "school.grading.scale.line",
        "scale_id",
        string="Grades",
        copy=True,
    )
    active = fields.Boolean(default=True)

    def _get_letter(self, percent):
        """Return the letter for a (rounded) percent, or an empty string."""
        self.ensure_one()
        for line in self.line_ids.sorted("min_percent", reverse=True):
            if percent >= line.min_percent:
                return line.letter
        return ""


class SchoolGradingScaleLine(models.Model):
    _name = "school.grading.scale.line"
    _description = "Grading Scale Line"
    _order = "min_percent desc"

    scale_id = fields.Many2one(
        "school.grading.scale",
        required=True,
        ondelete="cascade",
        index=True,
    )
    letter = fields.Char(
        string="Grade",
        required=True,
    )
    min_percent = fields.Float(
        string="From (%)",
        required=True,
        help="Lowest percent that earns this grade.",
    )
    gpa = fields.Float(
        string="GPA Points",
    )

    _min_unique = models.Constraint(
        "UNIQUE(scale_id, min_percent)",
        "Two grades of a scale can't start at the same percent.",
    )
