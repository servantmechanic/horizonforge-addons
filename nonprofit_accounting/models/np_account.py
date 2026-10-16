from odoo import api, fields, models

ACCOUNT_TYPES = [
    ("bank", "Bank/Cash"),
    ("liability", "Liability"),
    ("equity", "Equity"),
    ("income", "Income"),
    ("expense", "Expense"),
]


class NpAccount(models.Model):
    _name = "np.account"
    _description = "Account"
    _order = "code"
    _rec_names_search = ["code", "name"]

    code = fields.Char(required=True)
    name = fields.Char(required=True)
    account_type = fields.Selection(
        ACCOUNT_TYPES,
        string="Type",
        required=True,
    )
    active = fields.Boolean(default=True)
    note = fields.Text()

    _code_unique = models.Constraint(
        "UNIQUE(code)",
        "Account codes must be unique.",
    )

    @api.depends("code", "name")
    def _compute_display_name(self):
        for account in self:
            account.display_name = f"{account.code} {account.name}"
