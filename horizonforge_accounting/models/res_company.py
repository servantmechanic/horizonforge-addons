from odoo import fields, models

# (key, code, name, account type). Codes are padded with zeros to the chart's
# code length, so 5100 becomes 510000 on the 6-digit generic chart.
STARTER_ACCOUNTS = [
    ("equipment", "1511", "Equipment", "asset_fixed"),
    ("vehicles", "1512", "Vehicles", "asset_fixed"),
    ("accum_depr_equipment", "1515", "Accumulated Depreciation - Equipment", "asset_fixed"),
    ("accum_depr_vehicles", "1516", "Accumulated Depreciation - Vehicles", "asset_fixed"),
    ("credit_card", "2011", "Credit Card", "liability_credit_card"),
    ("owner_contributions", "3030", "Owner Contributions", "equity"),
    ("owner_draws", "3040", "Owner Draws", "equity"),
    ("job_materials", "5100", "Job Materials", "expense_direct_cost"),
    ("subcontractors", "5200", "Subcontractors", "expense_direct_cost"),
    ("job_labor", "5300", "Job Labor", "expense_direct_cost"),
    ("equipment_rental", "5400", "Equipment Rental", "expense_direct_cost"),
    ("permits", "5500", "Permits & Fees", "expense_direct_cost"),
    ("vehicle_fuel", "6130", "Vehicle & Fuel", "expense"),
    ("small_tools", "6140", "Small Tools & Supplies", "expense"),
    ("insurance", "6150", "Insurance", "expense"),
    ("utilities_phone", "6160", "Utilities & Phone", "expense"),
    ("professional_fees", "6170", "Professional Fees", "expense"),
    ("advertising", "6180", "Advertising", "expense"),
    ("office", "6190", "Office Expenses", "expense"),
    ("payroll_taxes", "6310", "Payroll Taxes", "expense"),
    ("depreciation", "6800", "Depreciation", "expense_depreciation"),
]


QB_VOUCHER_LAYOUT = "horizonforge_accounting.action_print_check_qb_voucher"


class ResCompany(models.Model):
    _inherit = "res.company"

    # Core keeps check layouts as report XML ids in this selection.
    account_check_printing_layout = fields.Selection(
        selection_add=[(QB_VOUCHER_LAYOUT, "QuickBooks Voucher Check (Top)")],
        ondelete={QB_VOUCHER_LAYOUT: "set default"},
    )

    def _hf_setup_accounting(self):
        """Add the starter accounts, journals, reconcile models and fiscal year.

        Safe to run again: anything that already exists, by code or by our
        XML id, is left alone, so renamed or archived records stay as they are.
        """
        for company in self.filtered("chart_template"):
            company = company.with_company(company)
            company._hf_setup_accounts()
            company._hf_setup_journals()
            company._hf_setup_reconcile_models()
            company._hf_setup_fiscal_year()
            company._hf_setup_check_layout()

    def _hf_xmlid(self, key):
        return f"horizonforge_accounting.{self.id}_{key}"

    def _hf_setup_accounts(self):
        Account = self.env["account.account"].with_context(active_test=False)
        sample = Account.search(Account._check_company_domain(self), limit=1)
        digits = len(sample.code) if sample else 6
        for key, code, name, account_type in STARTER_ACCOUNTS:
            code = code.ljust(digits, "0")
            if self.env.ref(self._hf_xmlid(key), raise_if_not_found=False):
                continue
            if Account.search_count([*Account._check_company_domain(self), ("code", "=", code)], limit=1):
                continue
            account = Account.create({
                "code": code,
                "name": name,
                "account_type": account_type,
                "company_ids": [(6, 0, self.ids)],
            })
            self.env["ir.model.data"]._update_xmlids([{
                "xml_id": self._hf_xmlid(key),
                "record": account,
                "noupdate": True,
            }])

    def _hf_setup_journals(self):
        Journal = self.env["account.journal"].with_context(active_test=False)
        domain = Journal._check_company_domain(self)
        card_account = self.env["account.account"].search([
            *self.env["account.account"]._check_company_domain(self),
            ("account_type", "=", "liability_credit_card"),
        ], limit=1)
        # Credit cards are bank journals on the card's liability account, not
        # core's "credit" type: OCA statement import and online feeds only
        # accept bank journals.
        journals = [
            ("savings", "SAV", "Savings", "bank", {}),
            ("credit_card", "CARD", "Credit Card", "bank", {"default_account_id": card_account.id}),
            ("petty_cash", "CSH1", "Petty Cash", "cash", {}),
        ]
        # Charts come with a bank journal, which serves as checking.
        if not Journal.search_count([*domain, ("type", "=", "bank")], limit=1):
            journals.insert(0, ("checking", "CHK", "Checking", "bank", {}))
        for key, code, name, journal_type, vals in journals:
            if self.env.ref(self._hf_xmlid(f"journal_{key}"), raise_if_not_found=False):
                continue
            if Journal.search_count([*domain, ("code", "=", code)], limit=1):
                continue
            journal = Journal.create({
                "name": name,
                "code": code,
                "type": journal_type,
                "company_id": self.id,
                **vals,
            })
            self.env["ir.model.data"]._update_xmlids([{
                "xml_id": self._hf_xmlid(f"journal_{key}"),
                "record": journal,
                "noupdate": True,
            }])

    def _hf_setup_reconcile_models(self):
        # Charts already come with Internal Transfers and Bank Fees.
        models_ = [
            ("reco_owner_draw", "Owner Draw", "owner_draws"),
            ("reco_owner_contribution", "Owner Contribution", "owner_contributions"),
        ]
        for key, name, account_key in models_:
            account = self.env.ref(self._hf_xmlid(account_key), raise_if_not_found=False)
            if not account or self.env.ref(self._hf_xmlid(key), raise_if_not_found=False):
                continue
            model = self.env["account.reconcile.model"].create({
                "name": name,
                "company_id": self.id,
                "line_ids": [(0, 0, {
                    "account_id": account.id,
                    "amount_type": "percentage",
                    "amount_string": "100",
                    "label": name,
                })],
            })
            self.env["ir.model.data"]._update_xmlids([{
                "xml_id": self._hf_xmlid(key),
                "record": model,
                "noupdate": True,
            }])

    def _hf_setup_check_layout(self):
        if self.account_check_printing_layout in (False, "disabled"):
            self.account_check_printing_layout = QB_VOUCHER_LAYOUT

    def _hf_setup_fiscal_year(self):
        FiscalYear = self.env["account.fiscal.year"]
        dates = self.compute_fiscalyear_dates(fields.Date.context_today(self))
        overlap = FiscalYear.search_count([
            ("company_id", "=", self.id),
            ("date_from", "<=", dates["date_to"]),
            ("date_to", ">=", dates["date_from"]),
        ], limit=1)
        if overlap:
            return
        if dates["date_from"].year == dates["date_to"].year:
            name = str(dates["date_to"].year)
        else:
            name = f"{dates['date_from'].year}-{dates['date_to'].year}"
        FiscalYear.create({
            "name": name,
            "date_from": dates["date_from"],
            "date_to": dates["date_to"],
            "company_id": self.id,
        })
