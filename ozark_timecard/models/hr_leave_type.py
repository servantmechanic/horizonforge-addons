from odoo import fields, models


class HrLeaveType(models.Model):
    _inherit = "hr.leave.type"

    timecard_paid = fields.Boolean(
        string="Paid (Timecard)",
        default=True,
        help="If checked, hours of this time off type taken during the "
        "timecard period are paid at the employee's regular rate on the "
        "Timecard report. Uncheck for unpaid leave types.",
    )
