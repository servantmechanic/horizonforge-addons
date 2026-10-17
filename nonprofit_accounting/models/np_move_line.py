from odoo import api, fields, models

# Line fields that feed the entry's generated bank lines.
SYNC_FIELDS = {"account_id", "amount"}


class NpMoveLine(models.Model):
    _name = "np.move.line"
    _description = "Journal Item"
    _order = "date desc, move_id desc, is_generated, id"

    move_id = fields.Many2one(
        "np.move",
        string="Entry",
        required=True,
        ondelete="cascade",
        index=True,
    )
    move_type = fields.Selection(
        string="Entry Type",
        related="move_id.move_type",
        store=True,
    )
    state = fields.Selection(
        related="move_id.state",
        store=True,
    )
    date = fields.Date(
        related="move_id.date",
        store=True,
        index=True,
    )
    company_id = fields.Many2one(related="move_id.company_id", store=True)
    currency_id = fields.Many2one(related="move_id.currency_id")
    account_id = fields.Many2one(
        "np.account",
        string="Account",
        required=True,
        ondelete="restrict",
        index=True,
    )
    account_type = fields.Selection(
        string="Account Type",
        related="account_id.account_type",
        store=True,
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        compute="_compute_partner_id",
        store=True,
        readonly=False,
        precompute=True,
    )
    name = fields.Char(string="Label")
    amount = fields.Monetary(
        currency_field="currency_id",
        help="Deposits and payments: the line amount. A negative amount "
        "reduces the total (e.g. a bank fee taken out of a deposit).",
    )
    debit = fields.Monetary(currency_field="currency_id", default=0.0)
    credit = fields.Monetary(currency_field="currency_id", default=0.0)
    balance = fields.Monetary(
        currency_field="currency_id",
        compute="_compute_balance",
        store=True,
        help="Debit minus credit.",
    )
    report_amount = fields.Monetary(
        string="Net Amount",
        currency_field="currency_id",
        compute="_compute_balance",
        store=True,
        help="Positive on the account's normal side: credits for income, "
        "liability and equity accounts; debits for bank and expense accounts.",
    )
    is_generated = fields.Boolean(
        string="Generated",
        readonly=True,
        help="Created automatically from the entry (e.g. the bank side of a deposit).",
    )

    _debit_credit_positive = models.Constraint(
        "CHECK(debit >= 0 AND credit >= 0)",
        "Debit and credit can't be negative.",
    )

    @api.depends("move_id.partner_id")
    def _compute_partner_id(self):
        for line in self:
            if line.move_id.move_type != "journal":
                line.partner_id = line.move_id.partner_id

    @api.depends("debit", "credit", "account_type")
    def _compute_balance(self):
        for line in self:
            line.balance = line.debit - line.credit
            if line.account_type in ("income", "liability", "equity"):
                line.report_amount = -line.balance
            else:
                line.report_amount = line.balance

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.move_id._check_draft()
        lines._sync_moves()
        return lines

    def write(self, vals):
        self.move_id._check_draft()
        res = super().write(vals)
        if SYNC_FIELDS & vals.keys():
            self._sync_moves()
        return res

    def unlink(self):
        moves = self.move_id
        res = super().unlink()
        self.browse()._sync_moves(moves)
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_draft_only(self):
        self.move_id._check_draft()

    def _sync_moves(self, moves=None):
        """Regenerate bank lines after items are edited directly (the entry
        form goes through np.move.write, which already does this)."""
        if self.env.context.get("np_syncing"):
            return
        if moves is None:
            moves = self.filtered(lambda line: not line.is_generated).move_id
        moves.exists()._sync_lines()
