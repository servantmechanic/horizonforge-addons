from odoo.exceptions import AccessError
from odoo.tests import TransactionCase, new_test_user, tagged

from odoo.addons.horizonforge_job_accounting.models.hf_job_profit_line import BURDEN_PARAM


@tagged("post_install", "-at_install")
class TestJobProfit(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Lumber Yard"})
        cls.employee = cls.env["hr.employee"].create({"name": "Crew", "wage": 20.0})
        cls.lumber = cls.env["product.product"].create({"name": "Lumber", "standard_price": 30.0})
        cls.order = cls.env["sale.order"].create({
            "partner_id": cls.customer.id,
            "order_line": [(0, 0, {
                "product_id": cls.env.ref("horizonforge_project_custom.product_tm").id,
                "product_uom_qty": 20,
                "price_unit": 40.0,
            })],
        })
        cls.order.action_confirm()
        cls.job = cls.order.order_line.project_id
        task = cls.env["project.task"].create({
            "name": "Work", "project_id": cls.job.id, "sale_line_id": cls.order.order_line.id,
        })
        # 10 hours at $20 wage, billed at $40.
        cls.timesheet = cls.env["account.analytic.line"].create({
            "name": "Framing", "task_id": task.id, "project_id": cls.job.id,
            "employee_id": cls.employee.id, "unit_amount": 10.0,
        })
        cls.bill = cls.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": cls.vendor.id,
            "invoice_date": "2026-10-01",
            "hf_project_id": cls.job.id,
            "invoice_line_ids": [(0, 0, {"product_id": cls.lumber.id, "quantity": 4, "price_unit": 30.0})],
        })
        cls.bill.action_post()
        cls.invoice = cls.order._create_invoices()
        cls.invoice.action_post()

    def _lines(self, **domain):
        return self.env["hf.job.profit.line"].search([
            ("project_id", "=", self.job.id),
            *[(fname, "=", value) for fname, value in domain.items()],
        ])

    def test_lines_by_category(self):
        lines = self._lines()
        totals = {cat: sum(lines.filtered(lambda l, c=cat: l.category == c).mapped("profit"))
                  for cat in ("revenue", "labor", "bills")}
        self.assertEqual(totals, {"revenue": 400.0, "labor": -200.0, "bills": -120.0})
        labor = self._lines(category="labor")
        self.assertEqual((labor.hours, labor.cost, labor.employee_id), (10.0, 200.0, self.employee))
        self.assertEqual(self._lines(category="revenue").move_id, self.invoice)
        self.assertEqual(self._lines(category="bills").move_id, self.bill)

    def test_project_totals(self):
        job = self.job
        self.assertEqual(job.hf_contract_amount, 800.0)
        self.assertEqual(job.hf_revenue, 400.0)
        self.assertEqual(job.hf_to_invoice, 0.0)
        self.assertEqual(job.hf_cost, 320.0)
        self.assertEqual(job.hf_profit, 80.0)
        self.assertAlmostEqual(job.hf_margin, 0.2)
        self.assertEqual(job.hf_hours, 10.0)

    def test_uninvoiced_time(self):
        self.env["account.analytic.line"].create({
            "name": "Trim", "task_id": self.job.tasks[:1].id, "project_id": self.job.id,
            "employee_id": self.employee.id, "unit_amount": 5.0,
        })
        self.job.invalidate_recordset()
        self.assertEqual(self.job.hf_to_invoice, 200.0)
        self.assertEqual(self.job.hf_hours, 15.0)

    def test_labor_burden(self):
        self.env["ir.config_parameter"].set_param(BURDEN_PARAM, "15")
        labor = self._lines(category="labor")
        self.assertAlmostEqual(labor.burden, 30.0)
        self.assertAlmostEqual(labor.cost, 230.0)
        self.job.invalidate_recordset()
        self.assertAlmostEqual(self.job.hf_profit, 50.0)

    def test_refund_reduces_revenue(self):
        refund = self.invoice._reverse_moves()
        refund.action_post()
        self.job.invalidate_recordset()
        self.assertEqual(self.job.hf_revenue, 0.0)

    def test_open_source(self):
        bill_line = self._lines(category="bills")
        self.assertEqual(bill_line.action_open_source()["res_id"], self.bill.id)
        labor = self._lines(category="labor")
        action = labor.action_open_source()
        self.assertEqual((action["res_model"], action["res_id"]), ("account.analytic.line", self.timesheet.id))

    def test_templates_excluded(self):
        template = self.env["project.project"].search([("is_template", "=", True)], limit=1)
        if template:
            self.assertFalse(self.env["hf.job.profit.line"].search_count([("project_id", "=", template.id)]))

    def test_access(self):
        manager = new_test_user(self.env, login="hf_pm", groups="project.group_project_manager")
        self.assertTrue(self.env["hf.job.profit.line"].with_user(manager).search_count([]))
        self.assertEqual(self.job.with_user(manager).hf_profit, 80.0)
        crew = new_test_user(self.env, login="hf_crew", groups="project.group_project_user")
        with self.assertRaises(AccessError):
            self.env["hf.job.profit.line"].with_user(crew).search([])
