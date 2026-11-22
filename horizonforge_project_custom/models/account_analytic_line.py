from odoo import api, fields, models


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

    @api.model
    def hf_get_running_timer(self):
        """Return the current user's running timer for the header icon.

        Timers come from the OCA module hr_timesheet_time_control, which marks
        a running timer as a line with a start time and no hours yet. Without
        it, or for users who cannot log time, the icon is not shown.
        """
        user = self.env.user
        if (
            "date_time" not in self._fields
            or not user.employee_ids
            or not user.has_group("hr_timesheet.group_hr_timesheet_user")
        ):
            return {"enabled": False}
        lines = self.search(self._running_domain(), order="date_time desc")
        line = lines[:1]
        if not line:
            return {"enabled": True, "running": False}
        return {
            "enabled": True,
            "running": True,
            "count": len(lines),
            "id": line.id,
            "name": line.name if line.name and line.name != "/" else "",
            "project": line.project_id.display_name,
            "job_code": line.project_id.hf_job_code or "",
            "task": line.task_id.display_name or "",
            "task_id": line.task_id.id,
            "start": fields.Datetime.to_string(line.date_time),
        }
