from odoo import fields, models


class AccountAnalyticLine(models.Model):
    _inherit = "account.analytic.line"

    hf_job_code = fields.Char(
        string="Job Code",
        related="project_id.hf_job_code",
    )

    def _show_portal_timesheets(self):
        return super()._show_portal_timesheets() and not self.env.user._hf_portal_toggle("portal_hide_timesheets")

    def _hourly_cost(self):
        # Labor cost is the employee's Wage ($/hr), as in the payroll report.
        # Billing never reads this: T&M invoices use the sales order line price.
        return self.employee_id.sudo().wage or super()._hourly_cost()
