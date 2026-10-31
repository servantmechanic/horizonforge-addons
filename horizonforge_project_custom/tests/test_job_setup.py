from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestJobSetup(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Customer"})
        cls.employee = cls.env["hr.employee"].create({"name": "Crew"})

    def _confirm_order(self, xmlid, price=1000.0):
        product = self.env.ref(f"horizonforge_project_custom.{xmlid}")
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1, "price_unit": price})],
        })
        order.action_confirm()
        return order

    def _check_job(self, order):
        project = order.order_line.project_id
        self.assertTrue(project)
        self.assertFalse(project.is_template)
        self.assertTrue(project.allow_timesheets)
        self.assertTrue(project.account_id)
        self.assertEqual(project.privacy_visibility, "portal")
        self.assertEqual(project.type_ids.mapped("name"), ["Estimate", "Scheduled", "In Progress", "Punch List", "Done"])
        return project

    def test_bid_job(self):
        order = self._confirm_order("product_bid")
        self._check_job(order)
        self.assertEqual(order.order_line.product_id.invoice_policy, "order")
        invoice = order._create_invoices()
        self.assertEqual(invoice.amount_untaxed, 1000.0)

    def test_progress_job(self):
        order = self._confirm_order("product_progress")
        self._check_job(order)
        line = order.order_line
        self.assertEqual(line.qty_delivered_method, "manual")
        line.qty_delivered = 0.25
        invoice = order._create_invoices()
        self.assertEqual(invoice.amount_untaxed, 250.0)

    def test_tm_job(self):
        order = self._confirm_order("product_tm", price=80.0)
        project = self._check_job(order)
        task = self.env["project.task"].create({"name": "Work", "project_id": project.id, "sale_line_id": order.order_line.id})
        self.env["account.analytic.line"].create({
            "name": "Work", "task_id": task.id, "project_id": project.id,
            "employee_id": self.employee.id, "unit_amount": 3.0,
        })
        self.assertEqual(order.order_line.qty_delivered, 3.0)
        invoice = order._create_invoices()
        self.assertEqual(invoice.amount_untaxed, 240.0)

    def test_each_job_gets_its_own_analytic_account(self):
        first = self._confirm_order("product_tm").order_line.project_id
        second = self._confirm_order("product_tm").order_line.project_id
        self.assertNotEqual(first.account_id, second.account_id)

    def test_closing_stage_marks_task_done(self):
        project = self._confirm_order("product_bid").order_line.project_id
        stage_map = {stage.name: stage for stage in project.type_ids}
        task = self.env["project.task"].create({
            "name": "Work", "project_id": project.id, "stage_id": stage_map["Estimate"].id,
        })
        task.stage_id = stage_map["Punch List"]
        self.assertFalse(task.is_closed)
        task.stage_id = stage_map["Done"]
        self.assertEqual(task.state, "1_done")

    def _log(self, order, employee, hours):
        project = order.order_line.project_id
        task = project.tasks[:1] or self.env["project.task"].create({
            "name": "Work", "project_id": project.id, "sale_line_id": order.order_line.id,
        })
        return self.env["account.analytic.line"].create({
            "name": "Work", "task_id": task.id, "project_id": project.id,
            "employee_id": employee.id, "unit_amount": hours,
        })

    def test_wage_is_cost_and_labor_price_is_billing(self):
        product = self.env.ref("horizonforge_project_custom.product_tm")
        product.list_price = 40.0
        order = self.env["sale.order"].create({
            "partner_id": self.customer.id,
            "order_line": [(0, 0, {"product_id": product.id, "product_uom_qty": 1})],
        })
        order.action_confirm()
        crew = self.env["hr.employee"].create([
            {"name": "Twenty", "wage": 20.0},
            {"name": "Twenty-five", "wage": 25.0},
            {"name": "Twenty-eight", "wage": 28.0},
        ])
        timesheets = self.env["account.analytic.line"]
        for employee in crew:
            timesheets |= self._log(order, employee, 10.0)
        self.assertEqual(timesheets.mapped("amount"), [-200.0, -250.0, -280.0])
        self.assertEqual(order.order_line.qty_delivered, 30.0)
        invoice = order._create_invoices()
        self.assertEqual(invoice.amount_untaxed, 1200.0)

    def test_wage_change_keeps_logged_cost_and_billing(self):
        order = self._confirm_order("product_tm", price=40.0)
        employee = self.env["hr.employee"].create({"name": "Raise", "wage": 20.0})
        timesheet = self._log(order, employee, 10.0)
        employee.wage = 30.0
        self.assertEqual(timesheet.amount, -200.0)
        self.assertEqual(self._log(order, employee, 10.0).amount, -300.0)
        self.assertEqual(order._create_invoices().amount_untaxed, 800.0)

    def test_hourly_cost_is_the_fallback(self):
        order = self._confirm_order("product_tm", price=40.0)
        employee = self.env["hr.employee"].create({"name": "No Wage", "hourly_cost": 15.0})
        self.assertEqual(self._log(order, employee, 2.0).amount, -30.0)

    def test_crew_user_logs_time_without_hr_rights(self):
        order = self._confirm_order("product_tm", price=40.0)
        user = new_test_user(self.env, login="hf_crew", groups="hr_timesheet.group_hr_timesheet_user")
        employee = self.env["hr.employee"].create({"name": "Crew User", "wage": 25.0, "user_id": user.id})
        project = order.order_line.project_id
        timesheet = self.env["account.analytic.line"].with_user(user).create({
            "name": "Work", "project_id": project.id, "employee_id": employee.id, "unit_amount": 2.0,
        })
        self.assertEqual(timesheet.sudo().amount, -50.0)
