import base64
import io
from datetime import timedelta

import xlsxwriter

from odoo import api, fields, models
from odoo.exceptions import UserError


class HfTimesheetPayrollWizard(models.TransientModel):
    _name = "hf.timesheet.payroll.wizard"
    _description = "Timesheet Payroll Report Wizard"

    employee_ids = fields.Many2many(
        "hr.employee",
        string="Employees",
        help="Leave empty to include every employee with timesheets in the period.",
    )
    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=6),
        help="Moved back to the start of its workweek, so overtime is always "
             "calculated on complete weeks.",
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=fields.Date.context_today,
        help="Moved forward to the end of its workweek.",
    )
    xlsx_file = fields.Binary(
        string="XLSX File",
        readonly=True,
        attachment=True,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from > wiz.date_to:
                raise UserError(self.env._("The start date must be before the end date."))

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def _get_settings(self):
        params = self.env["ir.config_parameter"].sudo()
        return {
            "ot_threshold": float(params.get_param("horizonforge_project_custom.ot_threshold", "40.0")),
            "ot_multiplier": float(params.get_param("horizonforge_project_custom.ot_multiplier", "1.5")),
            "week_start": int(params.get_param("horizonforge_project_custom.week_start", "6")),
        }

    def _week_start_date(self, day, week_start):
        return day - timedelta(days=(day.weekday() - week_start) % 7)

    def _get_period(self, week_start):
        self.ensure_one()
        first = self._week_start_date(self.date_from, week_start)
        last = self._week_start_date(self.date_to, week_start) + timedelta(days=6)
        return first, last

    def _get_timesheets(self, first, last):
        domain = [
            ("project_id", "!=", False),
            ("employee_id", "!=", False),
            ("date", ">=", first),
            ("date", "<=", last),
        ]
        if self.employee_ids:
            domain.append(("employee_id", "in", self.employee_ids.ids))
        return self.env["account.analytic.line"].sudo().search(domain)

    def _get_hourly_rate(self, emp):
        """Hourly rate from the Wage field, as in ozark_timecard (Wage = $/hr)."""
        return emp.sudo().wage or 0.0

    def _get_report_data(self):
        """Return one row per employee and week, plus job cost lines.

        A week's overtime premium is shared across its hours (the blended
        rate), so job costs add up to payroll whatever order hours were logged.
        """
        self.ensure_one()
        settings = self._get_settings()
        first, last = self._get_period(settings["week_start"])
        weekly = {}
        for line in self._get_timesheets(first, last):
            key = (self._week_start_date(line.date, settings["week_start"]), line.employee_id)
            weekly.setdefault(key, self.env["account.analytic.line"].sudo())
            weekly[key] |= line

        rows = []
        job_cost = {}
        for (week, emp), lines in sorted(weekly.items(), key=lambda item: (item[0][0], item[0][1].name)):
            total = sum(lines.mapped("unit_amount"))
            regular = min(total, settings["ot_threshold"])
            overtime = max(0.0, total - settings["ot_threshold"])
            rate = self._get_hourly_rate(emp)
            regular_pay = regular * rate
            overtime_pay = overtime * rate * settings["ot_multiplier"]
            cost = regular_pay + overtime_pay
            blended_rate = cost / total if total else 0.0

            hours_per_project = {}
            for line in lines:
                hours_per_project[line.project_id] = hours_per_project.get(line.project_id, 0.0) + line.unit_amount
                job = job_cost.setdefault((line.project_id, line.task_id), {"hours": 0.0, "cost": 0.0})
                job["hours"] += line.unit_amount
                job["cost"] += line.unit_amount * blended_rate
            rows.append({
                "employee": emp,
                "week_start": week,
                "week_end": week + timedelta(days=6),
                "projects": [
                    {"project": project, "hours": hours}
                    for project, hours in sorted(hours_per_project.items(), key=lambda item: item[0].name)
                ],
                "total": total,
                "regular": regular,
                "overtime": overtime,
                "rate": rate,
                "missing_wage": not rate,
                "regular_pay": regular_pay,
                "overtime_pay": overtime_pay,
                "cost": cost,
            })

        job_lines = [
            {"project": project, "task": task, **values}
            for (project, task), values in sorted(
                job_cost.items(), key=lambda item: (item[0][0].name, item[0][1].name or ""),
            )
        ]
        return {
            "rows": rows,
            "weeks": sorted({row["week_start"] for row in rows}),
            "job_lines": job_lines,
            "date_from": first,
            "date_to": last,
            "ot_threshold": settings["ot_threshold"],
            "ot_multiplier": settings["ot_multiplier"],
            "total_hours": sum(row["total"] for row in rows),
            "total_regular": sum(row["regular"] for row in rows),
            "total_overtime": sum(row["overtime"] for row in rows),
            "total_cost": sum(row["cost"] for row in rows),
            "currency": self.env.company.currency_id,
        }

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_print(self):
        self.ensure_one()
        return self.env.ref("horizonforge_project_custom.action_report_timesheet_payroll").report_action(self)

    def action_export_xlsx(self):
        self.ensure_one()
        self.xlsx_file = base64.b64encode(self._render_xlsx())
        filename = f"Payroll {self.date_from} to {self.date_to}.xlsx"
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self._name}/{self.id}/xlsx_file/{filename}?download=true",
            "target": "self",
        }

    def action_view_job_cost(self):
        self.ensure_one()
        data = self._get_report_data()
        lines = self.env["hf.job.cost.line"].create([{
            "wizard_id": self.id,
            "project_id": line["project"].id,
            "task_id": line["task"].id,
            "hours": line["hours"],
            "cost": line["cost"],
        } for line in data["job_lines"]])
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Job Cost"),
            "res_model": "hf.job.cost.line",
            "view_mode": "list",
            "domain": [("id", "in", lines.ids)],
            "context": {"group_by": ["project_id"]},
        }

    def _render_xlsx(self):
        data = self._get_report_data()
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        bold = workbook.add_format({"bold": True})
        hours = workbook.add_format({"num_format": "0.00"})
        money = workbook.add_format({"num_format": "#,##0.00"})
        day = workbook.add_format({"num_format": "yyyy-mm-dd"})

        sheet = workbook.add_worksheet("Payroll")
        headers = ["Week", "Employee", "Project", "Hours", "Total Hours", "Regular", "Overtime", "Hourly Wage", "Cost"]
        sheet.write_row(0, 0, headers, bold)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 2, 28)
        sheet.set_column(3, 8, 12)
        row_idx = 1
        for row in data["rows"]:
            for project_line in row["projects"]:
                sheet.write_datetime(row_idx, 0, fields.Datetime.to_datetime(row["week_start"]), day)
                sheet.write(row_idx, 1, row["employee"].name)
                sheet.write(row_idx, 2, project_line["project"].display_name)
                sheet.write_number(row_idx, 3, project_line["hours"], hours)
                row_idx += 1
            # Totals sit on the employee's last line, so sums do not double count.
            last = row_idx - 1
            sheet.write_number(last, 4, row["total"], hours)
            sheet.write_number(last, 5, row["regular"], hours)
            sheet.write_number(last, 6, row["overtime"], hours)
            sheet.write_number(last, 7, row["rate"], money)
            sheet.write_number(last, 8, row["cost"], money)
        sheet.write(row_idx, 0, "Total", bold)
        sheet.write_number(row_idx, 4, data["total_hours"], hours)
        sheet.write_number(row_idx, 5, data["total_regular"], hours)
        sheet.write_number(row_idx, 6, data["total_overtime"], hours)
        sheet.write_number(row_idx, 8, data["total_cost"], money)

        sheet = workbook.add_worksheet("Job Cost")
        sheet.write_row(0, 0, ["Job Code", "Project", "Task", "Hours", "Cost"], bold)
        sheet.set_column(0, 0, 12)
        sheet.set_column(1, 2, 32)
        sheet.set_column(3, 4, 12)
        for row_idx, line in enumerate(data["job_lines"], start=1):
            sheet.write(row_idx, 0, line["project"].hf_job_code or "")
            sheet.write(row_idx, 1, line["project"].display_name)
            sheet.write(row_idx, 2, line["task"].display_name or "")
            sheet.write_number(row_idx, 3, line["hours"], hours)
            sheet.write_number(row_idx, 4, line["cost"], money)
        workbook.close()
        return output.getvalue()


class HfJobCostLine(models.TransientModel):
    _name = "hf.job.cost.line"
    _description = "Job Cost Line"
    _order = "project_id, task_id"

    wizard_id = fields.Many2one(
        "hf.timesheet.payroll.wizard",
        string="Wizard",
        required=True,
        ondelete="cascade",
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        required=True,
    )
    hf_job_code = fields.Char(
        string="Job Code",
        related="project_id.hf_job_code",
    )
    task_id = fields.Many2one(
        "project.task",
        string="Task",
    )
    hours = fields.Float(
        string="Hours",
    )
    cost = fields.Monetary(
        string="Labor Cost",
        currency_field="currency_id",
        help="Hours at the week's blended rate, which includes the overtime premium.",
    )
    currency_id = fields.Many2one(
        "res.currency",
        default=lambda self: self.env.company.currency_id,
    )
