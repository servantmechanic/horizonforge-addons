from odoo.tests import tagged

from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.addons.horizonforge_accounting.models.res_company import STARTER_ACCOUNTS


@tagged("post_install", "-at_install")
class TestAccountingSetup(AccountTestInvoicingCommon):
    # The test company loads its chart in setUpClass, which runs the setup
    # through the chart template hook, the same way a new company does.

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.company_data["company"]

    def _ref(self, key):
        return self.env.ref(self.company._hf_xmlid(key), raise_if_not_found=False)

    def _accounts(self, **domain):
        Account = self.env["account.account"].with_context(active_test=False)
        return Account.search([
            *Account._check_company_domain(self.company),
            *[(fname, "=", value) for fname, value in domain.items()],
        ])

    def _journals(self, **domain):
        Journal = self.env["account.journal"].with_context(active_test=False)
        return Journal.search([
            ("company_id", "=", self.company.id),
            *[(fname, "=", value) for fname, value in domain.items()],
        ])

    def test_starter_accounts(self):
        for key, code, name, account_type in STARTER_ACCOUNTS:
            account = self._accounts(code=code.ljust(6, "0"))
            self.assertEqual(len(account), 1, name)
            created = self._ref(key)
            if created:
                self.assertEqual(account, created)
                self.assertEqual((account.name, account.account_type), (name, account_type))
        # The generic chart already has a credit card account at 201100.
        self.assertFalse(self._ref("credit_card"))
        self.assertEqual(self._ref("job_materials").code, "510000")

    def test_journals(self):
        self.assertEqual(self._journals(code="SAV").type, "bank")
        self.assertEqual(self._journals(code="CSH1").type, "cash")
        card = self._journals(code="CARD")
        self.assertEqual(card.type, "bank")
        self.assertEqual(card.default_account_id.account_type, "liability_credit_card")
        # The chart's own bank journal serves as checking.
        self.assertFalse(self._journals(code="CHK"))

    def test_checking_when_no_bank_journal(self):
        self._journals(type="bank").unlink()
        self.company._hf_setup_accounting()
        self.assertEqual(self._journals(code="CHK").type, "bank")
        self.assertTrue(self._journals(code="SAV"))
        self.assertTrue(self._journals(code="CARD"))

    def test_fiscal_year(self):
        years = self.env["account.fiscal.year"].search([("company_id", "=", self.company.id)])
        self.assertEqual(len(years), 1)
        today = self.env.cr.now().date()
        self.assertTrue(years.date_from <= today <= years.date_to)

    def test_rerun_creates_nothing(self):
        counts = (len(self._accounts()), len(self._journals()), self.env["account.fiscal.year"].search_count([]))
        self.company._hf_setup_accounting()
        self.assertEqual(
            (len(self._accounts()), len(self._journals()), self.env["account.fiscal.year"].search_count([])),
            counts,
        )

    def test_edits_and_deletions_are_kept(self):
        self._ref("job_materials").name = "Materials"
        self._ref("advertising").unlink()
        self._accounts(code="618000").unlink()
        marketing = self.env["account.account"].create({
            "code": "618000",
            "name": "Marketing",
            "account_type": "expense",
            "company_ids": [(6, 0, self.company.ids)],
        })
        self.company._hf_setup_accounting()
        self.assertEqual(self._ref("job_materials").name, "Materials")
        self.assertEqual(self._accounts(code="618000"), marketing)
        self.assertFalse(self._ref("advertising"))

    def test_main_company_set_up_on_install(self):
        company = self.env.ref("base.main_company")
        if not company.chart_template:
            self.skipTest("the main company has no chart of accounts")
        ref = self.env.ref(company._hf_xmlid("job_materials"), raise_if_not_found=False)
        self.assertTrue(ref)
