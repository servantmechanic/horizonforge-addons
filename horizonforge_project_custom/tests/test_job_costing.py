from odoo.tests import Form, TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestJobCosting(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Customer"})
        cls.vendor = cls.env["res.partner"].create({"name": "Lumber Yard"})
        cls.lumber = cls.env["product.product"].create({"name": "Lumber", "standard_price": 30.0})
        cls.job = cls._confirm_order("PO-778").order_line.project_id
        cls.other_job = cls._confirm_order(False).order_line.project_id

    @classmethod
    def _confirm_order(cls, reference):
        order = cls.env["sale.order"].create({
            "partner_id": cls.customer.id,
            "client_order_ref": reference,
            "order_line": [(0, 0, {
                "product_id": cls.env.ref("horizonforge_project_custom.product_tm").id,
                "product_uom_qty": 1,
                "price_unit": 40.0,
            })],
        })
        order.action_confirm()
        return order

    def _bill(self, job=None, lines=1):
        return self.env["account.move"].create({
            "move_type": "in_invoice",
            "partner_id": self.vendor.id,
            "invoice_date": "2026-10-01",
            "hf_project_id": job.id if job else False,
            "invoice_line_ids": [
                (0, 0, {"product_id": self.lumber.id, "quantity": 4, "price_unit": 30.0})
                for _ in range(lines)
            ],
        })

    def test_analytic_accounting_is_on_for_internal_users_only(self):
        self.assertTrue(new_test_user(self.env, login="hf_inside", groups="base.group_user").has_group("analytic.group_analytic_accounting"))
        self.assertFalse(new_test_user(self.env, login="hf_outside", groups="base.group_portal").has_group("analytic.group_analytic_accounting"))
        self.assertTrue(self.env["res.config.settings"].create({}).group_analytic_accounting)

    def test_job_code_is_numbered_and_replaces_customer_reference(self):
        self.assertRegex(self.job.hf_job_code, r"^J-\d{5}$")
        self.assertRegex(self.other_job.hf_job_code, r"^J-\d{5}$")
        self.assertNotEqual(self.job.hf_job_code, self.other_job.hf_job_code)
        self.assertEqual(self.job.account_id.code, self.job.hf_job_code)
        self.assertEqual(self.job.sale_order_id.client_order_ref, "PO-778")
        self.assertEqual(self.job.sale_order_id.hf_job_code, self.job.hf_job_code)

    def test_manual_project_is_numbered(self):
        project = self.env["project.project"].create({"name": "Walk-in Job"})
        self.assertRegex(project.hf_job_code, r"^J-\d{5}$")

    def test_templates_and_internal_project_are_not_numbered(self):
        template = self.env.ref("horizonforge_project_custom.template_tm")
        self.assertFalse(template.hf_job_code)
        internal = self.env.company.internal_project_id
        internal.account_id.code = False
        internal._hf_assign_job_codes()
        self.assertFalse(internal.hf_job_code)

    def test_existing_account_code_is_kept(self):
        account = self.env["account.analytic.account"].create({
            "name": "Old Job",
            "code": "ACME-1",
            "plan_id": self.job.account_id.plan_id.id,
        })
        project = self.env["project.project"].create({"name": "Old Job", "account_id": account.id})
        self.assertEqual(project.hf_job_code, "ACME-1")

    def test_edited_code_reaches_the_analytic_account(self):
        self.job.hf_job_code = "J-CUSTOM"
        self.assertEqual(self.job.account_id.code, "J-CUSTOM")

    def test_find_by_job_code(self):
        code = self.job.hf_job_code
        task = self.env["project.task"].create({"name": "Work", "project_id": self.job.id})
        employee = self.env["hr.employee"].create({"name": "Crew", "wage": 20.0})
        timesheet = self.env["account.analytic.line"].create({
            "name": "Work", "project_id": self.job.id, "employee_id": employee.id, "unit_amount": 1.0,
        })
        self.assertIn(self.job, self.env["project.project"].search([("hf_job_code", "=", code)]))
        self.assertIn(task, self.env["project.task"].search([("hf_job_code", "=", code)]))
        self.assertIn(timesheet, self.env["account.analytic.line"].search([("hf_job_code", "=", code)]))
        self.assertIn(self.job.sale_order_id, self.env["sale.order"].search([("hf_job_code", "=", code)]))
        self.assertIn(self.job.id, [row[0] for row in self.env["project.project"].name_search(code)])
        accounts = self.env["account.analytic.account"].name_search(code)
        self.assertIn(self.job.account_id.id, [row[0] for row in accounts])

    def test_job_on_bill_sets_every_line(self):
        bill = self._bill(self.job, lines=2)
        expected = {str(self.job.account_id.id): 100.0}
        self.assertEqual(bill.invoice_line_ids.mapped("analytic_distribution"), [expected, expected])

    def test_bill_posts_cost_to_the_job(self):
        bill = self._bill(self.job)
        bill.action_post()
        items = self.env["account.analytic.line"].search([("move_line_id", "in", bill.invoice_line_ids.ids)])
        self.assertEqual(items.mapped("amount"), [-120.0])
        self.assertEqual(items.account_id, self.job.account_id)
        costs = self.job.sudo()._get_profitability_items(False)["costs"]["data"]
        self.assertEqual(sum(cost.get("billed", 0.0) for cost in costs), -120.0)

    def test_changing_the_job_moves_the_lines(self):
        bill = self._bill(self.job)
        bill.hf_project_id = self.other_job
        self.assertEqual(bill.invoice_line_ids.analytic_distribution, {str(self.other_job.account_id.id): 100.0})

    def test_clearing_the_job_clears_the_lines(self):
        bill = self._bill(self.job)
        bill.hf_project_id = False
        self.assertFalse(bill.invoice_line_ids.analytic_distribution)

    def test_line_added_later_gets_the_job(self):
        bill = self._bill(self.job)
        bill.write({"invoice_line_ids": [(0, 0, {"name": "Nails", "quantity": 1, "price_unit": 5.0})]})
        self.assertEqual(len(bill.invoice_line_ids), 2)
        self.assertTrue(all(bill.invoice_line_ids.mapped("analytic_distribution")))

    def test_split_bill_keeps_line_distribution(self):
        bill = self._bill(lines=2)
        bill.invoice_line_ids[0].analytic_distribution = {str(self.job.account_id.id): 100.0}
        bill.invoice_line_ids[1].analytic_distribution = {str(self.other_job.account_id.id): 100.0}
        bill.action_post()
        self.assertEqual(
            bill.invoice_line_ids.mapped("analytic_distribution"),
            [{str(self.job.account_id.id): 100.0}, {str(self.other_job.account_id.id): 100.0}],
        )

    def test_bill_form_sets_lines(self):
        user = new_test_user(self.env, login="hf_bookkeeper", groups="account.group_account_invoice,project.group_project_user")
        move_form = Form(self.env["account.move"].with_user(user).with_context(default_move_type="in_invoice"))
        move_form.partner_id = self.vendor
        move_form.invoice_date = "2026-10-01"
        move_form.hf_project_id = self.job
        with move_form.invoice_line_ids.new() as line:
            line.name = "Lumber"
            line.price_unit = 30.0
        bill = move_form.save()
        self.assertEqual(bill.invoice_line_ids.analytic_distribution, {str(self.job.account_id.id): 100.0})

    def test_customer_invoice_is_unaffected(self):
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.customer.id,
            "invoice_line_ids": [(0, 0, {"name": "Work", "price_unit": 10.0})],
        })
        self.assertFalse(invoice.hf_project_id)
        self.assertFalse(invoice.invoice_line_ids.analytic_distribution)

    def test_bill_picker_shows_job_code(self):
        job = self.job.with_context(hf_show_job_code=True)
        self.assertTrue(job.display_name.startswith(f"[{self.job.hf_job_code}]"))
        self.assertNotIn(self.job.hf_job_code, self.job.display_name)
