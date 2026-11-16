from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_compare


class SchoolWeightScheme(models.Model):
    _name = "school.weight.scheme"
    _description = "Weight Scheme"
    _order = "name"

    name = fields.Char(required=True)
    method = fields.Selection(
        [
            ("average", "Average of percentages"),
            ("points", "Total points"),
        ],
        string="Calculation Method",
        default="average",
        required=True,
        help="Average of percentages: every assignment in a category counts "
        "equally. Total points: points earned divided by points possible, "
        "so bigger assignments count more.",
    )
    line_ids = fields.One2many(
        "school.weight.scheme.line",
        "scheme_id",
        string="Weights",
        copy=True,
    )
    active = fields.Boolean(default=True)

    @api.constrains("line_ids")
    def _check_total(self):
        for scheme in self:
            total = sum(scheme.line_ids.mapped("weight"))
            if scheme.line_ids and float_compare(total, 100.0, precision_digits=2):
                raise ValidationError(_(
                    "The weights of %(scheme)s add up to %(total)s. They must total 100.",
                    scheme=scheme.name,
                    total=f"{total:g}",
                ))


class SchoolWeightSchemeLine(models.Model):
    _name = "school.weight.scheme.line"
    _description = "Weight Scheme Line"
    _order = "sequence, id"

    scheme_id = fields.Many2one(
        "school.weight.scheme",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(related="category_id.sequence", store=True)
    category_id = fields.Many2one(
        "school.score.category",
        string="Category",
        required=True,
        ondelete="restrict",
    )
    weight = fields.Float(
        string="Weight (%)",
        required=True,
    )

    _category_unique = models.Constraint(
        "UNIQUE(scheme_id, category_id)",
        "A category can only appear once in a weight scheme.",
    )
    _weight_range = models.Constraint(
        "CHECK(weight >= 0 AND weight <= 100)",
        "A weight must be between 0 and 100.",
    )
