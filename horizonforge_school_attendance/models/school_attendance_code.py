from odoo import api, fields, models


class SchoolAttendanceCode(models.Model):
    _name = "school.attendance.code"
    _description = "Attendance Code"
    _order = "sequence, id"

    name = fields.Char(
        required=True,
        help="For example Absent or Half day.",
    )
    code = fields.Char(
        required=True,
        size=1,
        help="One letter: the key that records it in the attendance grid.",
    )
    kind = fields.Selection(
        [
            ("absent", "Absent"),
            ("tardy", "Tardy"),
        ],
        string="Counts As",
        default="absent",
        required=True,
    )
    absence_days = fields.Float(
        string="Days Absent",
        compute="_compute_absence_days",
        store=True,
        readonly=False,
        help="1 for a whole day, 0.5 for a part day.",
    )
    excused = fields.Boolean(
        help="Counted apart from unexcused absences on the reports.",
    )
    color = fields.Char(default="#e03131")
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Attendance code letters must be unique.",
    )
    _absence_days_range = models.Constraint(
        "CHECK(absence_days >= 0 AND absence_days <= 1)",
        "Days absent must be between 0 and 1.",
    )

    @api.depends("kind")
    def _compute_absence_days(self):
        for code in self:
            if code.kind == "tardy":
                code.absence_days = 0.0
            elif not code.absence_days:
                code.absence_days = 1.0

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("code"):
                vals["code"] = vals["code"].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get("code"):
            vals["code"] = vals["code"].strip().upper()
        return super().write(vals)
