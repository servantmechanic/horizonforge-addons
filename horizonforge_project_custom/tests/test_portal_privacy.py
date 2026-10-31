import re

from odoo.exceptions import AccessError
from odoo.tests import HttpCase, new_test_user, tagged

BASE = "horizonforge_project_custom"
TIME_FIELDS = ("effective_hours", "total_hours_spent", "timesheet_ids", "allocated_hours", "progress")
SALE_FIELDS = ("sale_line_id", "sale_order_id", "display_sale_order_button", "remaining_hours_so")
SHARING_VIEWS = (
    ("project.project_sharing_project_task_view_form", "form"),
    ("project.project_sharing_project_task_view_kanban", "kanban"),
    ("project.project_sharing_project_task_view_tree", "list"),
)
WAIT_FOR = """
const waitFor = (selector) => new Promise((resolve, reject) => {
    let tries = 0;
    const timer = setInterval(() => {
        const el = document.querySelector(selector);
        if (el) { clearInterval(timer); resolve(el); }
        else if (++tries > 100) { clearInterval(timer); reject(new Error("Not found: " + selector)); }
    }, 100);
});
"""


@tagged("post_install", "-at_install")
class TestPortalPrivacy(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.portal_user = new_test_user(cls.env, login="hf_portal", groups="base.group_portal")
        cls.partner = cls.portal_user.partner_id
        cls.env["ir.config_parameter"].sudo().set_param("sale.default_invoice_email_template", False)
        cls.employee = cls.env["hr.employee"].create({"name": "Crew"})
        cls.project = cls.env["project.project"].create({
            "name": "Job",
            "privacy_visibility": "portal",
            "allow_timesheets": True,
            "partner_id": cls.partner.id,
            "type_ids": [(0, 0, {"name": "To Do"})],
        })
        cls.project.message_subscribe([cls.partner.id])
        cls.task = cls.env["project.task"].create({
            "name": "Framing",
            "project_id": cls.project.id,
            "allocated_hours": 10.0,
        })
        cls.env["account.analytic.line"].create({
            "name": "Secret work entry",
            "project_id": cls.project.id,
            "task_id": cls.task.id,
            "employee_id": cls.employee.id,
            "unit_amount": 7.0,
        })
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.partner.id,
            "order_line": [(0, 0, {
                "product_id": cls.env.ref(f"{BASE}.product_bid").id,
                "product_uom_qty": 1,
                "price_unit": 100.0,
            })],
        })
        cls.order._portal_ensure_token()
        cls.order.state = "sent"

    def _toggle(self, name, value):
        self.env["ir.config_parameter"].sudo().set_param(f"{BASE}.{name}", value)
        self.env.registry.clear_cache()

    def _portal_get(self, url):
        self.authenticate("hf_portal", "hf_portal")
        return self.url_open(url, allow_redirects=False)

    def _counters(self, *names):
        self.authenticate("hf_portal", "hf_portal")
        return self.make_jsonrpc_request("/my/counters", {"counters": list(names)})

    def test_defaults(self):
        self.assertTrue(self.env.user._hf_portal_toggle("portal_hide_timesheets"))
        self.assertTrue(self.env.user._hf_portal_toggle("auto_follow_tasks"))
        self.assertFalse(self.env.user._hf_portal_toggle("portal_hide_sales_orders"))

    def test_unticking_a_default_on_toggle_survives_settings(self):
        settings = self.env["res.config.settings"].create({"hf_portal_hide_timesheets": False})
        settings.execute()
        self.assertFalse(self.env.user._hf_portal_toggle("portal_hide_timesheets"))
        self.assertFalse(self.env["res.config.settings"].create({}).hf_portal_hide_timesheets)

    def test_task_page_hides_time(self):
        self.assertIn(self.partner, self.task.message_partner_ids)
        response = self._portal_get(f"/my/tasks/{self.task.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Framing", response.text)
        self.assertNotIn("Timesheets", response.text)
        self.assertNotIn("Secret work entry", response.text)
        self.assertNotIn("Allocated Time", response.text)

    def test_task_page_shows_time_when_off(self):
        self._toggle("portal_hide_timesheets", False)
        response = self._portal_get(f"/my/tasks/{self.task.id}")
        self.assertIn("Secret work entry", response.text)

    def test_project_page_hides_time(self):
        response = self._portal_get(f"/my/projects/{self.project.id}")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Framing", response.text)
        self.assertNotIn("Time Spent", response.text)

    def test_timesheet_routes_blocked(self):
        for url in ("/my/timesheets", f"/my/tasks/{self.task.id}?report_type=pdf"):
            response = self._portal_get(url)
            self.assertEqual(response.status_code, 303, url)
            self.assertTrue(response.headers["Location"].endswith("/my"), url)
        self.assertEqual(self._counters("timesheet_count")["timesheet_count"], 0)

    def test_timesheet_fields_blocked_in_data(self):
        task = self.task.with_user(self.portal_user)
        for field in TIME_FIELDS:
            with self.assertRaises(AccessError, msg=field):
                task.read([field])
        self.assertTrue(task.read(["name"]))
        self.assertFalse(set(TIME_FIELDS) & set(task.fields_get()))
        self.assertFalse(set(TIME_FIELDS) & set(task.search_read([("id", "=", task.id)])[0]))

    def test_timesheet_fields_open_when_off(self):
        self._toggle("portal_hide_timesheets", False)
        self.assertEqual(self.task.with_user(self.portal_user).read(["effective_hours"])[0]["effective_hours"], 7.0)

    def test_internal_users_unaffected(self):
        staff = new_test_user(self.env, login="hf_pm", groups="project.group_project_manager")
        self.assertEqual(self.task.with_user(staff).effective_hours, 7.0)
        self._toggle("portal_hide_sales_orders", True)
        sales = new_test_user(self.env, login="hf_sales", groups="sales_team.group_sale_manager")
        self.assertTrue(self.order.with_user(sales).read(["name"]))

    def test_timesheet_lines_blocked_over_rpc(self):
        with self.assertRaises(AccessError):
            self.env["account.analytic.line"].with_user(self.portal_user).search_read([])

    def _sharing_arch(self, xmlid, view_type):
        task_model = self.env["project.task"].with_user(self.portal_user)
        return task_model.get_view(self.env.ref(xmlid).id, view_type)["arch"]

    def _assert_arch_clean(self, names):
        pattern = re.compile(r"\b(%s)\b" % "|".join(names))
        for xmlid, view_type in SHARING_VIEWS:
            self.assertFalse(pattern.findall(self._sharing_arch(xmlid, view_type)), xmlid)

    def test_views_drop_time_fields(self):
        self.project._add_collaborators(self.partner)
        self._assert_arch_clean(TIME_FIELDS + ("remaining_hours", "subtask_effective_hours"))
        self._toggle("portal_hide_timesheets", False)
        self.assertIn('name="effective_hours"', self._sharing_arch(*SHARING_VIEWS[0]))

    def test_views_drop_sale_fields(self):
        self._toggle("portal_hide_timesheets", False)
        self._toggle("portal_hide_sales_orders", True)
        self._assert_arch_clean(SALE_FIELDS)
        self.assertIn('name="effective_hours"', self._sharing_arch(*SHARING_VIEWS[0]))

    def _open_task_in_browser(self, check):
        self.project._add_collaborators(self.partner, limited_access=True)
        code = WAIT_FOR + """
        (async () => {
            (await waitFor(".o_kanban_record, .o_data_row")).click();
            await waitFor(".o_form_view .o_field_widget[name='name']");
            const text = document.body.innerText;
            %s
            console.log("test successful");
        })();
        """ % check
        self.browser_js(f"/my/projects/{self.project.id}/project_sharing", code, login="hf_portal")

    def test_project_sharing_in_browser(self):
        """Dropping fields must leave project sharing working for the customer."""
        self._toggle("portal_hide_sales_orders", True)
        self._open_task_in_browser("""
            if (/Time Spent|Timesheets|Allocated Time|Sales Order/.test(text)) {
                throw new Error("Hidden information on the task form");
            }
        """)

    def test_project_sharing_in_browser_toggles_off(self):
        """The same page shows the time when the toggle is off."""
        self._toggle("portal_hide_timesheets", False)
        self._open_task_in_browser("""
            if (!text.includes("Timesheets")) {
                throw new Error("Timesheets tab missing");
            }
        """)

    def test_orders_visible_by_default(self):
        self.assertEqual(self._counters("quotation_count")["quotation_count"], 1)
        self.assertEqual(self._portal_get("/my/quotes").status_code, 200)

    def test_sales_order_routes_blocked(self):
        self._toggle("portal_hide_sales_orders", True)
        for url in ("/my/orders", "/my/quotes"):
            response = self._portal_get(url)
            self.assertEqual(response.status_code, 303, url)
            self.assertTrue(response.headers["Location"].endswith("/my"), url)
        counters = self._counters("quotation_count", "order_count")
        self.assertEqual(counters, {"quotation_count": 0, "order_count": 0})

    def test_order_without_token_blocked(self):
        self._toggle("portal_hide_sales_orders", True)
        response = self._portal_get(f"/my/orders/{self.order.id}")
        self.assertEqual(response.status_code, 303)
        self.assertTrue(response.headers["Location"].endswith("/my"))

    def test_order_with_token_opens(self):
        self._toggle("portal_hide_sales_orders", True)
        url = f"/my/orders/{self.order.id}?access_token={self.order.access_token}"
        response = self._portal_get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.order.name, response.text)
        self.authenticate(None, None)
        response = self.url_open(url, allow_redirects=False)
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.order.name, response.text)

    def test_order_blocked_over_rpc(self):
        self._toggle("portal_hide_sales_orders", True)
        self.assertFalse(self.env["sale.order"].with_user(self.portal_user).search([]))
        with self.assertRaises(AccessError):
            self.order.with_user(self.portal_user).read(["name"])

    def test_task_has_no_sales_order_data(self):
        self.task.sale_line_id = self.order.order_line
        self._toggle("portal_hide_sales_orders", True)
        task = self.task.with_user(self.portal_user)
        with self.assertRaises(AccessError):
            task.read(["sale_line_id"])
        response = self._portal_get(f"/my/tasks/{self.task.id}")
        self.assertNotIn(self.order.get_portal_url(), response.text)

    def test_task_list_has_no_sales_order_filters(self):
        self._toggle("portal_hide_sales_orders", True)
        response = self._portal_get(f"/my/projects/{self.project.id}")
        self.assertNotIn("Sales Order Item", response.text)

    def test_invoices_stay_visible(self):
        self._toggle("portal_hide_sales_orders", True)
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner.id,
            "invoice_line_ids": [(0, 0, {"name": "Work", "price_unit": 100.0, "quantity": 1})],
        })
        invoice.action_post()
        self.assertEqual(self._portal_get("/my/invoices").status_code, 200)
        self.assertIn(invoice.name, self._portal_get("/my/invoices").text)
