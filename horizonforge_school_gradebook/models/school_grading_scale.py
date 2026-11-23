from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


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

    def _entry_percent(self, letter):
        """The percent a letter typed in the gradebook counts for, or None
        when the scale has no such letter."""
        self.ensure_one()
        letter = (letter or "").strip().upper()
        line = self.line_ids.filtered(lambda l: (l.letter or "").strip().upper() == letter)[:1]
        return line.entry_percent if line else None

    def _recompute_letter_scores(self):
        """Scores typed as letters follow their scale's values."""
        scores = self.env["school.score"].sudo().search([
            ("assignment_id.entry_mode", "=", "letter"), ("letter_entered", "!=", False),
        ])
        if scores:
            self.env.add_to_compute(scores._fields["percent"], scores)

    def _get_key(self, decimals=0):
        """The scale as printed on the report card:
        ``[{"letter", "range", "description"}]``, highest first."""
        self.ensure_one()
        step = 10 ** -decimals
        key = []
        upper = 100
        for line in self.line_ids.sorted("min_percent", reverse=True):
            if line.min_percent <= 0:
                text = _("%(upper)s and below", upper=f"{upper:g}")
            else:
                text = f"{line.min_percent:g}-{upper:g}"
            key.append({"letter": line.letter, "range": text, "description": line.description or ""})
            upper = round(line.min_percent - step, decimals)
        return key


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
    entry_percent = fields.Float(
        string="Value When Entered (%)",
        compute="_compute_entry_percent",
        store=True,
        readonly=False,
        help="What this letter counts for when a teacher types it in the "
        "gradebook (an essay graded A-). By default the middle of its range; "
        "for the lowest grade, 5 below the top of its range. Changing the "
        "ranges sets them back to these defaults.",
    )
    gpa = fields.Float(
        string="GPA Points",
    )
    description = fields.Char(
        help="Printed in the key on the report card, for example Excellent Work.",
    )

    _min_unique = models.Constraint(
        "UNIQUE(scale_id, min_percent)",
        "Two grades of a scale can't start at the same percent.",
    )

    @api.depends("min_percent", "scale_id.line_ids.min_percent")
    def _compute_entry_percent(self):
        for line in self:
            lines = line.scale_id.line_ids.sorted("min_percent")
            higher = lines.filtered(lambda l: l.min_percent > line.min_percent)
            upper = min(higher.mapped("min_percent")) if higher else 100.0
            if lines and line.min_percent == lines[0].min_percent and upper - 5 >= line.min_percent:
                line.entry_percent = upper - 5  # the lowest grade: F counts 55, not 30
            else:
                line.entry_percent = (line.min_percent + upper) / 2

    @api.constrains("entry_percent")
    def _check_entry_percent(self):
        for line in self:
            if not 0 <= line.entry_percent <= 100:
                raise ValidationError(_(
                    "%(letter)s: the value when entered must be from 0 to 100.", letter=line.letter,
                ))

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.scale_id._recompute_letter_scores()
        return lines

    def write(self, vals):
        res = super().write(vals)
        if {"letter", "min_percent", "entry_percent"} & set(vals):
            self.scale_id._recompute_letter_scores()
        return res

