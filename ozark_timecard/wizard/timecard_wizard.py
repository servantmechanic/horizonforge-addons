from datetime import datetime, timedelta

import pytz

from odoo import api, fields, models
from odoo.exceptions import UserError


class HrTimecardWizard(models.TransientModel):
    _name = "hr.timecard.wizard"
    _description = "Timecard Report Wizard"

    employee_ids = fields.Many2many(
        "hr.employee",
        string="Employees",
        default=lambda self: self._default_employees(),
        help="Leave empty to include all active employees with hours or "
        "time off in the period.",
    )
    report_style = fields.Selection(
        [
            ("both", "Summary + Detailed Timecards"),
            ("summary", "Payroll Summary Only"),
            ("detail", "Detailed Timecards Only"),
        ],
        string="Report Style",
        default="both",
        required=True,
    )
    date_from = fields.Date(
        string="From",
        required=True,
        default=lambda self: fields.Date.context_today(self) - timedelta(days=13),
    )
    date_to = fields.Date(
        string="To",
        required=True,
        default=fields.Date.context_today,
    )
    ot_threshold = fields.Float(
        string="OT Threshold (hrs/week)",
        default=40.0,
        required=True,
    )
    ot_multiplier = fields.Float(
        string="OT Multiplier",
        default=1.5,
        required=True,
    )
    week_start = fields.Selection(
        [
            ("6", "Sunday"),
            ("0", "Monday"),
        ],
        string="Week Starts On",
        default="6",
        required=True,
        help="Weekly overtime is calculated per workweek starting on this day.",
    )

    def _default_employees(self):
        if self.env.context.get("active_model") == "hr.employee":
            return [(6, 0, self.env.context.get("active_ids", []))]
        return False

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wiz in self:
            if wiz.date_from > wiz.date_to:
                raise UserError("The start date must be before the end date.")

    def action_print(self):
        self.ensure_one()
        return self.env.ref("ozark_timecard.action_report_timecard").report_action(self)

    # ------------------------------------------------------------------
    # Computation
    # ------------------------------------------------------------------

    def _get_hourly_rate(self, emp):
        """Hourly rate from the employee's Payroll tab.

        Enterprise-style fields are preferred when present (an hourly
        wage amount). On Community, where those fields may not exist,
        the plain Wage field is used directly as the hourly rate.
        Returns 0.0 when no wage is set; the report flags it.
        """
        hourly = getattr(emp, "hourly_wage", 0.0) or 0.0
        if hourly:
            return hourly
        return getattr(emp, "wage", 0.0) or 0.0

    def _get_tz(self, emp):
        return pytz.timezone(emp.tz or self.env.user.tz or "UTC")

    def _local_bounds_utc(self, emp):
        """Return naive-UTC datetimes covering [date_from 00:00, date_to 24:00) local."""
        tz = self._get_tz(emp)
        start_local = tz.localize(
            datetime.combine(self.date_from, datetime.min.time())
        )
        end_local = tz.localize(
            datetime.combine(self.date_to + timedelta(days=1), datetime.min.time())
        )
        return (
            start_local.astimezone(pytz.utc).replace(tzinfo=None),
            end_local.astimezone(pytz.utc).replace(tzinfo=None),
        )

    def _week_start_date(self, local_date):
        ws = int(self.week_start)
        offset = (local_date.weekday() - ws) % 7
        return local_date - timedelta(days=offset)

    def _get_employees(self):
        self.ensure_one()
        if self.employee_ids:
            return self.employee_ids.sorted("name")
        return self.env["hr.employee"].search([], order="name")

    def _get_employee_data(self, emp):
        """Compute one employee's timecard data for the wizard period."""
        tz = self._get_tz(emp)
        start_utc, end_utc = self._local_bounds_utc(emp)

        # ---------------- Attendance ----------------
        attendances = self.env["hr.attendance"].search(
            [
                ("employee_id", "=", emp.id),
                ("check_in", ">=", start_utc),
                ("check_in", "<", end_utc),
                ("check_out", "!=", False),
            ],
            order="check_in",
        )

        weeks = {}
        days = {}
        for att in attendances:
            check_in_local = pytz.utc.localize(att.check_in).astimezone(tz)
            check_out_local = pytz.utc.localize(att.check_out).astimezone(tz)
            local_date = check_in_local.date()
            wk = self._week_start_date(local_date)
            weeks.setdefault(wk, 0.0)
            weeks[wk] += att.worked_hours
            day = days.setdefault(local_date, {"pairs": [], "hours": 0.0})
            day["pairs"].append(
                (
                    check_in_local.strftime("%I:%M %p").lstrip("0"),
                    check_out_local.strftime("%I:%M %p").lstrip("0"),
                )
            )
            day["hours"] += att.worked_hours

        # One row per day; punch pairs are laid out across paired columns.
        max_pairs = max([len(d["pairs"]) for d in days.values()] or [0])
        max_pairs = max(max_pairs, 2)
        day_lines = []
        for local_date in sorted(days):
            day = days[local_date]
            pairs = list(day["pairs"])
            pairs += [("", "")] * (max_pairs - len(pairs))
            day_lines.append(
                {
                    "date": local_date,
                    "weekday": local_date.strftime("%a"),
                    "pairs": pairs,
                    "hours": day["hours"],
                }
            )

        week_lines = []
        total_reg = total_ot = 0.0
        for wk in sorted(weeks):
            worked = weeks[wk]
            reg = min(worked, self.ot_threshold)
            ot = max(0.0, worked - self.ot_threshold)
            total_reg += reg
            total_ot += ot
            week_lines.append(
                {
                    "week_start": wk,
                    "week_end": wk + timedelta(days=6),
                    "worked": worked,
                    "regular": reg,
                    "overtime": ot,
                }
            )

        # ---------------- Time Off taken in period ----------------
        leaves = self.env["hr.leave"].search(
            [
                ("employee_id", "=", emp.id),
                ("state", "=", "validate"),
                ("request_date_from", "<=", self.date_to),
                ("request_date_to", ">=", self.date_from),
            ]
        )

        hours_per_day = emp.resource_calendar_id.hours_per_day or 8.0
        leave_lines = []
        paid_leave_hours = 0.0
        unpaid_leave_hours = 0.0
        for leave in leaves:
            l_from = max(leave.request_date_from, self.date_from)
            l_to = min(leave.request_date_to, self.date_to)
            total_days = (leave.request_date_to - leave.request_date_from).days + 1
            overlap_days = (l_to - l_from).days + 1
            leave_hours = getattr(leave, "number_of_hours", 0.0) or (
                leave.number_of_days * hours_per_day
            )
            hours_in_period = leave_hours * (overlap_days / total_days)
            is_paid = leave.holiday_status_id.timecard_paid
            if is_paid:
                paid_leave_hours += hours_in_period
            else:
                unpaid_leave_hours += hours_in_period
            leave_lines.append(
                {
                    "type": leave.holiday_status_id.name,
                    "date_from": l_from,
                    "date_to": l_to,
                    "hours": hours_in_period,
                    "paid": is_paid,
                }
            )

        # ---------------- Time Off balances ----------------
        alloc_types = (
            self.env["hr.leave.allocation"]
            .search(
                [
                    ("employee_id", "=", emp.id),
                    ("state", "=", "validate"),
                ]
            )
            .mapped("holiday_status_id")
        )
        balance_lines = []
        for ltype in alloc_types:
            ltype_ctx = ltype.with_context(employee_id=emp.id)
            try:
                remaining = ltype_ctx.virtual_remaining_leaves
                allocated = ltype_ctx.max_leaves
                taken = ltype_ctx.leaves_taken
            except Exception:
                remaining = allocated = taken = 0.0
            unit = "hours" if ltype.request_unit == "hour" else "days"
            balance_lines.append(
                {
                    "type": ltype.name,
                    "allocated": allocated,
                    "taken": taken,
                    "remaining": remaining,
                    "unit": unit,
                }
            )

        # ---------------- Pay ----------------
        rate = self._get_hourly_rate(emp)
        reg_pay = total_reg * rate
        ot_pay = total_ot * rate * self.ot_multiplier
        pto_pay = paid_leave_hours * rate

        return {
            "employee": emp,
            "day_lines": day_lines,
            "max_pairs": max_pairs,
            "pair_headers": list(range(1, max_pairs + 1)),
            "week_lines": week_lines,
            "total_reg": total_reg,
            "total_ot": total_ot,
            "total_worked": total_reg + total_ot,
            "leave_lines": leave_lines,
            "paid_leave_hours": paid_leave_hours,
            "unpaid_leave_hours": unpaid_leave_hours,
            "balance_lines": balance_lines,
            "rate": rate,
            "missing_wage": not rate,
            "ot_rate": rate * self.ot_multiplier,
            "reg_pay": reg_pay,
            "ot_pay": ot_pay,
            "pto_pay": pto_pay,
            "gross_pay": reg_pay + ot_pay + pto_pay,
        }

    def _get_report_data(self):
        self.ensure_one()
        explicit = bool(self.employee_ids)
        details = []
        for emp in self._get_employees():
            data = self._get_employee_data(emp)
            has_activity = data["day_lines"] or data["leave_lines"]
            # When covering all employees, skip those with nothing in
            # the period; explicitly selected employees always appear.
            if not explicit and not has_activity:
                continue
            details.append(data)

        totals = {
            "total_reg": sum(d["total_reg"] for d in details),
            "total_ot": sum(d["total_ot"] for d in details),
            "paid_leave_hours": sum(d["paid_leave_hours"] for d in details),
            "reg_pay": sum(d["reg_pay"] for d in details),
            "ot_pay": sum(d["ot_pay"] for d in details),
            "pto_pay": sum(d["pto_pay"] for d in details),
            "gross_pay": sum(d["gross_pay"] for d in details),
        }
        return {
            "details": details,
            "totals": totals,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "ot_multiplier": self.ot_multiplier,
            "ot_threshold": self.ot_threshold,
            "show_summary": self.report_style in ("both", "summary"),
            "show_detail": self.report_style in ("both", "detail"),
            "currency": self.env.company.currency_id,
        }
