from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.mis_builder.models.accounting_none import AccountingNone


@tagged("post_install", "-at_install")
class TestFinancialReports(AccountTestInvoicingCommon):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]
        ref = lambda key: cls.env.ref(cls.company._hf_xmlid(key))  # noqa: E731
        bank = cls.company_data["default_journal_bank"].default_account_id
        receivable = cls.company_data["default_account_receivable"]
        payable = cls.company_data["default_account_payable"]
        income = cls.company_data["default_account_revenue"]
        cls._entry("2025-06-01", [(bank, 300), (income, -300)])
        cls._entry("2026-10-05", [(receivable, 1000), (income, -1000)])
        cls._entry("2026-10-06", [(ref("job_materials"), 400), (payable, -400)])
        cls._entry("2026-10-07", [(ref("advertising"), 100), (bank, -100)])
        cls._entry("2026-10-08", [(bank, 5000), (ref("owner_contributions"), -5000)])

    @classmethod
    def _entry(cls, date, lines):
        move = cls.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "journal_id": cls.company_data["default_journal_misc"].id,
            "line_ids": [
                (0, 0, {
                    "account_id": account.id,
                    "debit": max(amount, 0),
                    "credit": max(-amount, 0),
                })
                for account, amount in lines
            ],
        })
        move.action_post()

    def _instance(self, report_xmlid, date_from, date_to):
        return self.env["mis.report.instance"].create({
            "name": "Test",
            "report_id": self.env.ref(f"horizonforge_accounting.{report_xmlid}").id,
            "company_id": self.company.id,
            "period_ids": [(0, 0, {
                "name": "Period",
                "mode": "fix",
                "manual_date_from": date_from,
                "manual_date_to": date_to,
            })],
        })

    def _values(self, instance):
        values = {}
        for row in instance._compute_matrix().iter_rows():
            if not row.account_id:
                cell = next(row.iter_cells())
                values[row.kpi.name] = cell.val if cell else AccountingNone
        return values

    def test_profit_and_loss(self):
        values = self._values(self._instance("mis_report_pl", "2026-10-01", "2026-10-31"))
        expected = {
            "revenue": 1000,
            "cogs": 400,
            "gross_profit": 600,
            "gross_margin": 0.6,
            "expenses": 100,
            "operating_income": 500,
            "net_income": 500,
        }
        for name, amount in expected.items():
            self.assertAlmostEqual(values[name], amount, msg=name)

    def test_balance_sheet_balances(self):
        values = self._values(self._instance("mis_report_bs", "2026-10-01", "2026-10-31"))
        expected = {
            "cash": 5200,
            "receivable": 1000,
            "total_assets": 6200,
            "payable": 400,
            "total_liabilities": 400,
            "equity": 5000,
            "retained": 300,
            "current_earnings": 500,
            "total_le": 6200,
        }
        for name, amount in expected.items():
            self.assertAlmostEqual(values[name], amount, msg=name)
        self.assertAlmostEqual(values["out_of_balance"] or 0.0, 0.0)

    def test_rule_above_totals(self):
        Style = self.env["mis.report.style"]
        total = Style.merge([
            self.env.ref("horizonforge_accounting.mis_style_report"),
            self.env.ref("horizonforge_accounting.mis_style_total"),
        ])
        self.assertIn("border-top", Style.to_css_style(total))
        line = Style.merge([
            self.env.ref("horizonforge_accounting.mis_style_report"),
            self.env.ref("horizonforge_accounting.mis_style_line"),
        ])
        self.assertNotIn("border-top", Style.to_css_style(line) or "")

    def test_compact_pdf_layout(self):
        instance = self._instance("mis_report_bs", "2026-10-01", "2026-10-31")
        html = self.env["ir.actions.report"]._render_qweb_html(
            "mis_builder.qweb_pdf_export", instance.ids
        )[0].decode()
        self.assertIn("hf_compact", html)
        self.assertIn(self.company.name, html)
        self.assertIn("As of", html)
        self.assertIn("border-top", html)

    def test_shipped_instances_compute(self):
        for xmlid in ("mis_instance_pl", "mis_instance_pl_monthly", "mis_instance_bs"):
            instance = self.env.ref(f"horizonforge_accounting.{xmlid}")
            self.assertTrue(instance._compute_matrix(), xmlid)
            action = instance.preview()
            self.assertEqual((action["res_model"], action["res_id"]), ("mis.report.instance", instance.id))
