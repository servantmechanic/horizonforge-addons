import base64
import io
from datetime import date, timedelta
from zipfile import ZipFile

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, TransactionCase, new_test_user, tagged

# A Wednesday; with the default Sunday week start its week begins on 2026-06-07.
WEDNESDAY = date(2026, 6, 10)
SUNDAY = date(2026, 6, 7)


@tagged("post_install", "-at_install")
class TestPayroll(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.emp_a = cls.env["hr.employee"].create({"name": "Avery", "wage": 20.0})
        cls.emp_b = cls.env["hr.employee"].create({"name": "Blake", "wage": 30.0})
        cls.job_1 = cls.env["project.project"].create({"name": "Job 1"})
        cls.job_2 = cls.env["project.project"].create({"name": "Job 2"})
        cls.task_1 = cls.env["project.task"].create({"name": "Task 1", "project_id": cls.job_1.id})
        cls.wizard = cls.env["hf.timesheet.payroll.wizard"].create({"date_from": WEDNESDAY, "date_to": WEDNESDAY})

    def _log(self, employee, project, hours, day=WEDNESDAY, task=None):
        return self.env["account.analytic.line"].create({
            "name": "Work", "employee_id": employee.id, "project_id": project.id,
            "task_id": task.id if task else False, "unit_amount": hours, "date": day,
        })

    def _row(self, data, employee):
        return next(row for row in data["rows"] if row["employee"] == employee)

    def test_overtime_over_threshold(self):
        self._log(self.emp_a, self.job_1, 45.0)
        self._log(self.emp_b, self.job_1, 30.0)
        data = self.wizard._get_report_data()
        row_a = self._row(data, self.emp_a)
        self.assertEqual((row_a["regular"], row_a["overtime"]), (40.0, 5.0))
        self.assertEqual(row_a["cost"], 40 * 20 + 5 * 20 * 1.5)
        row_b = self._row(data, self.emp_b)
        self.assertEqual((row_b["regular"], row_b["overtime"]), (30.0, 0.0))
        self.assertEqual(row_b["cost"], 900.0)

    def test_settings_change_overtime(self):
        params = self.env["ir.config_parameter"].sudo()
        params.set_param("horizonforge_project_custom.ot_threshold", "35")
        params.set_param("horizonforge_project_custom.ot_multiplier", "2")
        self._log(self.emp_a, self.job_1, 40.0)
        row = self._row(self.wizard._get_report_data(), self.emp_a)
        self.assertEqual(row["overtime"], 5.0)
        self.assertEqual(row["cost"], 35 * 20 + 5 * 20 * 2)

    def test_partial_period_uses_whole_week(self):
        self._log(self.emp_a, self.job_1, 30.0, day=SUNDAY)
        self._log(self.emp_a, self.job_1, 15.0, day=WEDNESDAY)
        data = self.wizard._get_report_data()
        self.assertEqual(data["date_from"], SUNDAY)
        self.assertEqual(data["date_to"], SUNDAY + timedelta(days=6))
        self.assertEqual(self._row(data, self.emp_a)["overtime"], 5.0)

    def test_week_start_monday(self):
        self.env["ir.config_parameter"].sudo().set_param("horizonforge_project_custom.week_start", "0")
        self._log(self.emp_a, self.job_1, 30.0, day=SUNDAY)
        self._log(self.emp_a, self.job_1, 15.0, day=WEDNESDAY)
        self.wizard.date_from = SUNDAY
        data = self.wizard._get_report_data()
        self.assertEqual(len(data["weeks"]), 2)
        self.assertEqual(data["total_overtime"], 0.0)

    def test_grouped_by_week_employee_project(self):
        self._log(self.emp_a, self.job_2, 2.0)
        self._log(self.emp_a, self.job_1, 3.0)
        self._log(self.emp_a, self.job_1, 1.0)
        self._log(self.emp_b, self.job_1, 1.0)
        data = self.wizard._get_report_data()
        self.assertEqual([row["employee"] for row in data["rows"]], [self.emp_a, self.emp_b])
        projects = data["rows"][0]["projects"]
        self.assertEqual([(line["project"], line["hours"]) for line in projects], [(self.job_1, 4.0), (self.job_2, 2.0)])

    def test_job_cost_matches_payroll_and_spreads_premium(self):
        self._log(self.emp_a, self.job_1, 30.0, task=self.task_1)
        self._log(self.emp_a, self.job_2, 20.0)
        data = self.wizard._get_report_data()
        # 40 at $20 plus 10 at $30 is $1,100 over 50 hours: a blended $22.
        costs = {line["project"]: line["cost"] for line in data["job_lines"]}
        self.assertAlmostEqual(costs[self.job_1], 660.0)
        self.assertAlmostEqual(costs[self.job_2], 440.0)
        self.assertAlmostEqual(sum(costs.values()), data["total_cost"])

    def test_job_cost_view(self):
        self._log(self.emp_a, self.job_1, 8.0, task=self.task_1)
        action = self.wizard.action_view_job_cost()
        line = self.env["hf.job.cost.line"].search(action["domain"])
        self.assertEqual((line.project_id, line.task_id, line.hours, line.cost), (self.job_1, self.task_1, 8.0, 160.0))

    def test_missing_wage_flagged(self):
        employee = self.env["hr.employee"].create({"name": "No Wage"})
        self._log(employee, self.job_1, 8.0)
        self.assertTrue(self._row(self.wizard._get_report_data(), employee)["missing_wage"])

    def test_employee_filter(self):
        self._log(self.emp_a, self.job_1, 8.0)
        self._log(self.emp_b, self.job_1, 8.0)
        self.wizard.employee_ids = self.emp_b
        self.assertEqual([row["employee"] for row in self.wizard._get_report_data()["rows"]], [self.emp_b])

    def test_xlsx_export(self):
        self._log(self.emp_a, self.job_1, 45.0)
        action = self.wizard.action_export_xlsx()
        self.assertIn("xlsx_file", action["url"])
        with ZipFile(io.BytesIO(base64.b64decode(self.wizard.xlsx_file))) as xlsx:
            self.assertIn("xl/worksheets/sheet2.xml", xlsx.namelist())

    def test_pdf_template_renders(self):
        self._log(self.emp_a, self.job_1, 45.0, task=self.task_1)
        html = self.env["ir.actions.report"]._render_qweb_html(
            "horizonforge_project_custom.report_timesheet_payroll", self.wizard.ids,
        )[0].decode()
        self.assertIn("Avery", html)
        self.assertIn("Job Cost", html)

    def test_timesheet_manager_can_run_without_hr_rights(self):
        user = new_test_user(self.env, login="hf_office", groups="hr_timesheet.group_timesheet_manager")
        self.assertFalse(user.has_group("hr.group_hr_manager"))
        self._log(self.emp_a, self.job_1, 10.0)
        wizard = self.env["hf.timesheet.payroll.wizard"].with_user(user).create(
            {"date_from": WEDNESDAY, "date_to": WEDNESDAY},
        )
        self.assertEqual(wizard._get_report_data()["total_cost"], 200.0)

    def test_regular_timesheet_user_is_blocked(self):
        user = new_test_user(self.env, login="hf_crew", groups="hr_timesheet.group_hr_timesheet_user")
        with self.assertRaises(AccessError):
            self.env["hf.timesheet.payroll.wizard"].with_user(user).create(
                {"date_from": WEDNESDAY, "date_to": WEDNESDAY},
            )


@tagged("post_install", "-at_install")
class TestPayrollDownload(HttpCase):

    def test_xlsx_url_downloads_for_owner_only(self):
        new_test_user(self.env, login="hf_office", groups="hr_timesheet.group_timesheet_manager")
        new_test_user(self.env, login="hf_other", groups="base.group_user")
        self.env.flush_all()
        office = self.env["res.users"].search([("login", "=", "hf_office")])
        wizard = self.env["hf.timesheet.payroll.wizard"].with_user(office).create(
            {"date_from": WEDNESDAY, "date_to": WEDNESDAY},
        )
        url = wizard.action_export_xlsx()["url"]
        self.authenticate("hf_office", "hf_office")
        response = self.url_open(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content[:2], b"PK")
        self.assertIn(".xlsx", response.headers["Content-Disposition"])
        self.authenticate("hf_other", "hf_other")
        self.assertNotEqual(self.url_open(url).status_code, 200)
