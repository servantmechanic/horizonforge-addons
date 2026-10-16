from odoo import _, api, fields, models

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

    # Dashboard
    currency_id = fields.Many2one("res.currency", compute="_compute_currency_id")
    balance = fields.Monetary(
        compute="_compute_balance",
        currency_field="currency_id",
        help="Balance of posted entries.",
    )
    draft_count = fields.Integer(compute="_compute_draft_count")
    show_unpaid_bills = fields.Boolean(compute="_compute_unpaid_bills")
    unpaid_bill_count = fields.Integer(compute="_compute_unpaid_bills")
    unpaid_bill_total = fields.Monetary(
        compute="_compute_unpaid_bills",
        currency_field="currency_id",
    )

    @api.depends("code", "name")
    def _compute_display_name(self):
        for account in self:
            account.display_name = f"{account.code} {account.name}"

    def _compute_currency_id(self):
        self.currency_id = self.env.company.currency_id

    def _compute_balance(self):
        balances = dict(self.env["np.move.line"]._read_group(
            [("account_id", "in", self.ids), ("state", "=", "posted")],
            ["account_id"],
            ["balance:sum"],
        ))
        for account in self:
            account.balance = balances.get(account, 0.0)

    def _draft_domain(self):
        return [
            ("state", "=", "draft"),
            ("move_type", "!=", "payment"),
            "|",
            ("bank_account_id", "in", self.ids),
            ("dest_account_id", "in", self.ids),
        ]

    def _compute_draft_count(self):
        Move = self.env["np.move"]
        for account in self:
            account.draft_count = Move.search_count(account._draft_domain())

    def _compute_unpaid_bills(self):
        """The unpaid-bills summary shows on one card: the default payment
        account, or the first bank account."""
        company = self.env.company
        main_account = company.np_default_payment_account_id or self.search(
            [("account_type", "=", "bank")], limit=1
        )
        [(count, total)] = self.env["np.move"]._read_group(
            [("move_type", "=", "payment"), ("state", "=", "draft")],
            aggregates=["__count", "amount_total:sum"],
        )
        for account in self:
            account.show_unpaid_bills = account == main_account
            account.unpaid_bill_count = count
            account.unpaid_bill_total = total

    # -------------------------------------------------------------------------
    # Dashboard actions
    # -------------------------------------------------------------------------

    def _new_move_action(self, name, move_type, **defaults):
        self.ensure_one()
        context = {f"default_{key}": value for key, value in defaults.items()}
        return {
            "type": "ir.actions.act_window",
            "name": name,
            "res_model": "np.move",
            "views": [(False, "form")],
            "context": dict(context, default_move_type=move_type),
        }

    def action_new_deposit(self):
        return self._new_move_action(_("New Deposit"), "deposit", bank_account_id=self.id)

    def action_new_bill(self):
        return self._new_move_action(_("New Bill"), "payment", bank_account_id=self.id)

    def action_new_transfer(self):
        return self._new_move_action(_("New Transfer"), "transfer", bank_account_id=self.id)

    def action_open_entries(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "nonprofit_accounting.np_move_line_action"
        )
        action["name"] = self.display_name
        action["domain"] = [("account_id", "=", self.id)]
        action["context"] = {"search_default_posted": 1}
        return action

    def action_open_drafts(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "nonprofit_accounting.np_move_action_all"
        )
        action["name"] = _("Drafts: %s", self.display_name)
        action["domain"] = self._draft_domain()
        return action

    def action_open_unpaid_bills(self):
        return self.env["ir.actions.act_window"]._for_xml_id(
            "nonprofit_accounting.np_move_action_bill"
        )
