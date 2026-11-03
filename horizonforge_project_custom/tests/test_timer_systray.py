from datetime import timedelta

from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestTimerSystray(HttpCase):
    """The header timer needs the OCA module hr_timesheet_time_control."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.timer_module = "date_time" in cls.env["account.analytic.line"]._fields
        cls.user = new_test_user(
            cls.env, login="hf_crew_timer", groups="hr_timesheet.group_hr_timesheet_user",
        )
        cls.employee = cls.env["hr.employee"].create({"name": "Crew", "user_id": cls.user.id, "wage": 20.0})
        cls.project = cls.env["project.project"].create({"name": "Kitchen Remodel"})
        cls.task = cls.env["project.task"].create({"name": "Demo", "project_id": cls.project.id})

    def _timer(self, user=None, hours_ago=1.0, task=None):
        user = user or self.user
        return self.env["account.analytic.line"].with_user(user).create({
            "name": "Tear out cabinets",
            "project_id": self.project.id,
            "task_id": (task or self.task).id,
            "employee_id": user.employee_ids[:1].id,
            "date_time": fields.Datetime.now() - timedelta(hours=hours_ago),
            "unit_amount": 0,
        })

    def _get(self, user=None):
        return self.env["account.analytic.line"].with_user(user or self.user).hf_get_running_timer()

    def _require_timer_module(self):
        if not self.timer_module:
            self.skipTest("hr_timesheet_time_control is not installed")

    def test_hidden_without_timer_module(self):
        if self.timer_module:
            self.skipTest("hr_timesheet_time_control is installed")
        self.assertEqual(self._get(), {"enabled": False})

    def test_hidden_for_users_who_cannot_log_time(self):
        self._require_timer_module()
        office = new_test_user(self.env, login="hf_no_timesheets", groups="base.group_user")
        self.env["hr.employee"].create({"name": "Office", "user_id": office.id})
        self.assertEqual(self._get(office), {"enabled": False})
        no_employee = new_test_user(self.env, login="hf_no_employee", groups="hr_timesheet.group_hr_timesheet_user")
        self.assertEqual(self._get(no_employee), {"enabled": False})

    def test_no_timer_running(self):
        self._require_timer_module()
        self.assertEqual(self._get(), {"enabled": True, "running": False})

    def test_running_timer(self):
        self._require_timer_module()
        line = self._timer()
        result = self._get()
        self.assertTrue(result["running"])
        self.assertEqual(result["id"], line.id)
        self.assertEqual(result["project"], self.project.display_name)
        self.assertEqual(result["job_code"], self.project.hf_job_code)
        self.assertEqual(result["task_id"], self.task.id)
        self.assertEqual(result["name"], "Tear out cabinets")
        self.assertEqual(result["count"], 1)

    def test_stopped_timer_is_not_shown(self):
        self._require_timer_module()
        line = self._timer()
        line.with_user(self.user).button_end_work()
        self.assertGreater(line.unit_amount, 0.9)
        self.assertFalse(self._get()["running"])

    def test_other_users_timer_is_not_shown(self):
        self._require_timer_module()
        other = new_test_user(self.env, login="hf_other_crew", groups="hr_timesheet.group_hr_timesheet_user")
        self.env["hr.employee"].create({"name": "Other", "user_id": other.id})
        self._timer(user=other)
        self.assertFalse(self._get()["running"])

    def test_latest_of_several_timers_is_shown(self):
        self._require_timer_module()
        self._timer(hours_ago=3.0)
        later_task = self.env["project.task"].create({"name": "Framing", "project_id": self.project.id})
        latest = self._timer(hours_ago=1.0, task=later_task)
        result = self._get()
        self.assertEqual((result["id"], result["count"]), (latest.id, 2))

    def test_stop_from_header_in_browser(self):
        self._require_timer_module()
        line = self._timer(hours_ago=1.25)
        code = """
        const waitFor = (selector) => new Promise((resolve, reject) => {
            let tries = 0;
            const timer = setInterval(() => {
                const el = document.querySelector(selector);
                if (el) { clearInterval(timer); resolve(el); }
                else if (++tries > 100) { clearInterval(timer); reject(new Error("Not found: " + selector)); }
            }, 100);
        });
        (async () => {
            const elapsed = await waitFor(".o_hf_timer_elapsed");
            if (elapsed.textContent.trim() !== "1:15") {
                throw new Error("Elapsed shows " + elapsed.textContent);
            }
            (await waitFor(".o_hf_timer_systray")).click();
            const menu = await waitFor(".o_hf_timer_menu");
            if (!menu.textContent.includes("Kitchen Remodel") || !menu.textContent.includes("Demo")) {
                throw new Error("Menu content: " + menu.textContent);
            }
            (await waitFor(".o_hf_timer_stop")).click();
            await waitFor(".o_notification");
            (await waitFor(".o_hf_timer_systray")).click();
            await waitFor(".o_hf_timer_start");
            console.log("test successful");
        })();
        """
        self.browser_js("/odoo", code, login="hf_crew_timer")
        self.assertAlmostEqual(line.unit_amount, 1.25, delta=0.05)

    def test_start_work_from_header_in_browser(self):
        self._require_timer_module()
        code = """
        const waitFor = (selector) => new Promise((resolve, reject) => {
            let tries = 0;
            const timer = setInterval(() => {
                const el = document.querySelector(selector);
                if (el) { clearInterval(timer); resolve(el); }
                else if (++tries > 100) { clearInterval(timer); reject(new Error("Not found: " + selector)); }
            }, 100);
        });
        (async () => {
            const button = await waitFor(".o_hf_timer_systray");
            if (document.querySelector(".o_hf_timer_elapsed")) {
                throw new Error("Elapsed time shown with no timer running");
            }
            button.click();
            (await waitFor(".o_hf_timer_start")).click();
            await waitFor(".modal .o_form_view .o_field_widget[name='project_id']");
            console.log("test successful");
        })();
        """
        self.browser_js("/odoo", code, login="hf_crew_timer")
