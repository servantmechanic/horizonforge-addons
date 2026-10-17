from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import float_is_zero


def _default_date_from(model):
    today = fields.Date.context_today(model)
    return today.replace(day=1) - relativedelta(months=1)


def _default_date_to(model):
    return fields.Date.context_today(model).replace(day=1) - relativedelta(days=1)


class NpPeriodReport(models.TransientModel):
    _name = "np.period.report"
    _description = "Period Report"

    date_from = fields.Date(required=True, default=_default_date_from)
    date_to = fields.Date(required=True, default=_default_date_to)
    bank_account_ids = fields.Many2many(
        "np.account",
        string="Bank Accounts",
        domain=[("account_type", "=", "bank")],
        help="Leave empty for all bank and cash accounts.",
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )

    @api.constrains("date_from", "date_to")
    def _check_dates(self):
        for wizard in self:
            if wizard.date_from > wizard.date_to:
                raise ValidationError(_("The start date must be on or before the end date."))

    def action_print(self):
        return self.env.ref("nonprofit_accounting.action_report_period").report_action(self)

    def action_view(self):
        return self.env.ref("nonprofit_accounting.action_report_period_html").report_action(self)

    def _get_bank_accounts(self):
        return self.bank_account_ids or self.env["np.account"].with_context(
            active_test=False
        ).search([("account_type", "=", "bank")])

    def _get_report_data(self):
        """Cash-basis period summary for the selected bank/cash accounts.

        Every posted entry in the period that touches a selected account is
        split by its other lines: income and expense accounts, other bank
        accounts (transfers) and anything else (liabilities, equity). Entries
        that never touch a selected account are not cash and are left out.
        """
        self.ensure_one()
        Line = self.env["np.move.line"]
        currency = self.company_id.currency_id
        banks = self._get_bank_accounts()
        posted = [("state", "=", "posted"), ("company_id", "=", self.company_id.id)]

        def bank_balances(date_domain):
            return dict(Line._read_group(
                posted + [("account_id", "in", banks.ids)] + date_domain,
                ["account_id"],
                ["balance:sum"],
            ))

        beginning = bank_balances([("date", "<", self.date_from)])
        ending = bank_balances([("date", "<=", self.date_to)])

        period_moves = Line.search(posted + [
            ("account_id", "in", banks.ids),
            ("date", ">=", self.date_from),
            ("date", "<=", self.date_to),
        ]).move_id
        counterparts = Line._read_group(
            [("move_id", "in", period_moves.ids), ("account_id", "not in", banks.ids)],
            ["account_id"],
            ["balance:sum"],
        )

        sections = {"income": [], "expense": [], "transfer": [], "other": []}
        for account, balance in sorted(counterparts, key=lambda group: group[0].code):
            if float_is_zero(balance, precision_rounding=currency.rounding):
                continue
            cash_effect = -balance
            if account.account_type == "income":
                sections["income"].append({"account": account, "amount": cash_effect})
            elif account.account_type == "expense":
                sections["expense"].append({"account": account, "amount": -cash_effect})
            elif account.account_type == "bank":
                sections["transfer"].append({"account": account, "amount": cash_effect})
            else:
                sections["other"].append({"account": account, "amount": cash_effect})

        totals = {key: sum(row["amount"] for row in rows) for key, rows in sections.items()}
        beginning_total = sum(beginning.values())
        ending_total = sum(ending.values())
        calculated_ending = (
            beginning_total
            + totals["income"]
            - totals["expense"]
            + totals["transfer"]
            + totals["other"]
        )
        difference = currency.round(ending_total - calculated_ending)

        return {
            "currency": currency,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "all_accounts": not self.bank_account_ids,
            "bank_rows": [
                {
                    "account": bank,
                    "beginning": beginning.get(bank, 0.0),
                    "ending": ending.get(bank, 0.0),
                }
                for bank in banks.sorted("code")
                if bank in self.bank_account_ids
                or not currency.is_zero(beginning.get(bank, 0.0))
                or not currency.is_zero(ending.get(bank, 0.0))
            ],
            "beginning": beginning_total,
            "ending": ending_total,
            "income_rows": sections["income"],
            "expense_rows": sections["expense"],
            "transfer_rows": sections["transfer"],
            "other_rows": sections["other"],
            "total_income": totals["income"],
            "total_expense": totals["expense"],
            "total_transfer": totals["transfer"],
            "total_other": totals["other"],
            "net_change": totals["income"] - totals["expense"],
            "difference": difference,
            "balanced": float_is_zero(difference, precision_rounding=currency.rounding),
        }
