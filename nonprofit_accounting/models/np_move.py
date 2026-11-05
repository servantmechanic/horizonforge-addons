from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools import float_compare, float_is_zero
from odoo.tools.misc import format_date

MOVE_TYPES = [
    ("deposit", "Deposit"),
    ("payment", "Payment"),
    ("transfer", "Transfer"),
    ("journal", "Journal Entry"),
]

# Fields that can't change once an entry is posted.
LOCKED_FIELDS = {
    "move_type",
    "date",
    "bank_account_id",
    "dest_account_id",
    "amount",
    "partner_id",
    "ref",
    "check_number",
    "bill_date",
    "memo",
    "line_ids",
    "item_line_ids",
}

# Fields that feed the generated bank lines.
SYNC_FIELDS = LOCKED_FIELDS - {"ref", "check_number", "bill_date"}


def debit_credit(balance):
    """Split a signed balance (positive = debit) into debit/credit values."""
    return {"debit": max(balance, 0.0), "credit": max(-balance, 0.0)}


class NpMove(models.Model):
    _name = "np.move"
    _description = "Entry"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date desc, id desc"

    name = fields.Char(
        string="Number",
        default="/",
        readonly=True,
        copy=False,
        tracking=True,
        help="Assigned when the entry is first posted.",
    )
    move_type = fields.Selection(
        MOVE_TYPES,
        string="Type",
        required=True,
        readonly=True,
        default="journal",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("posted", "Posted")],
        string="Status",
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )
    date = fields.Date(
        required=True,
        default=fields.Date.context_today,
        tracking=True,
        help="The date the entry hits the books. For payments, the paid date.",
    )
    bill_date = fields.Date(
        default=fields.Date.context_today,
        tracking=True,
        help="Payments: the date of the bill or invoice being paid.",
    )
    payment_state = fields.Selection(
        [("unpaid", "Unpaid"), ("paid", "Paid")],
        compute="_compute_payment_state",
        store=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    bank_account_id = fields.Many2one(
        "np.account",
        string="Bank Account",
        domain=[("account_type", "=", "bank")],
        tracking=True,
        help="Deposits and payments: the bank or cash account. "
        "Transfers: the account the money comes from.",
    )
    dest_account_id = fields.Many2one(
        "np.account",
        string="To Account",
        domain=[("account_type", "=", "bank")],
        tracking=True,
        help="Transfers: the account the money goes to.",
    )
    amount = fields.Monetary(
        string="Transfer Amount",
        currency_field="currency_id",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Contact",
        tracking=True,
    )
    ref = fields.Char(
        string="Reference",
        help="Payments: the bill or invoice number. Others: deposit slip number, etc.",
    )
    check_number = fields.Char(
        string="Check #",
        tracking=True,
        copy=False,
    )
    memo = fields.Char()
    partner_default_account_id = fields.Many2one(
        "np.account",
        compute="_compute_partner_default_account_id",
        help="Pre-filled on new lines: the contact's default income account "
        "(deposits) or expense account (payments).",
    )
    line_ids = fields.One2many(
        "np.move.line",
        "move_id",
        string="Journal Items",
        copy=False,
    )
    item_line_ids = fields.One2many(
        "np.move.line",
        "move_id",
        string="Lines",
        domain=[("is_generated", "=", False)],
        copy=True,
        help="The lines you enter. Bank lines are generated from these.",
    )
    amount_total = fields.Monetary(
        string="Total",
        compute="_compute_amount_total",
        store=True,
        currency_field="currency_id",
        tracking=True,
    )

    @api.depends("name", "move_type")
    def _compute_display_name(self):
        type_labels = dict(MOVE_TYPES)
        for move in self:
            if move.name and move.name != "/":
                move.display_name = move.name
            else:
                move.display_name = _("Draft %s", type_labels.get(move.move_type, ""))

    @api.depends("move_type", "partner_id")
    def _compute_partner_default_account_id(self):
        for move in self:
            if move.move_type == "deposit":
                move.partner_default_account_id = move.partner_id.np_income_account_id
            elif move.move_type == "payment":
                move.partner_default_account_id = move.partner_id.np_expense_account_id
            else:
                move.partner_default_account_id = False

    @api.depends("move_type", "state")
    def _compute_payment_state(self):
        for move in self:
            if move.move_type != "payment":
                move.payment_state = False
            else:
                move.payment_state = "paid" if move.state == "posted" else "unpaid"

    @api.depends("move_type", "amount", "item_line_ids.amount", "item_line_ids.debit")
    def _compute_amount_total(self):
        for move in self:
            if move.move_type == "transfer":
                move.amount_total = move.amount
            elif move.move_type == "journal":
                move.amount_total = sum(move.item_line_ids.mapped("debit"))
            else:
                move.amount_total = sum(move.item_line_ids.mapped("amount"))

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        moves = super().create(vals_list)
        moves._sync_lines()
        return moves

    def write(self, vals):
        if LOCKED_FIELDS & vals.keys():
            self._check_draft()
        res = super().write(vals)
        if SYNC_FIELDS & vals.keys():
            self._sync_lines()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_only_new_drafts(self):
        for move in self:
            if move.state == "posted" or move.name != "/":
                raise UserError(_(
                    "%s has been posted, so it can't be deleted. Reset it to "
                    "draft and correct it, or record a correcting entry.",
                    move.display_name,
                ))

    # -------------------------------------------------------------------------
    # Generated lines
    # -------------------------------------------------------------------------

    def _sync_lines(self):
        """Keep the generated bank lines (and item debit/credit) in step with
        the entry. Only touches draft entries."""
        self = self.with_context(np_syncing=True)
        Line = self.env["np.move.line"]
        for move in self.filtered(lambda m: m.state == "draft"):
            items = move.item_line_ids
            if move.move_type == "transfer":
                items.unlink()
            elif move.move_type in ("deposit", "payment"):
                sign = -1 if move.move_type == "deposit" else 1
                for item in items:
                    vals = debit_credit(sign * item.amount)
                    if (item.debit, item.credit) != (vals["debit"], vals["credit"]):
                        item.write(vals)

            wanted = move._generated_line_vals()
            generated = move.line_ids.filtered("is_generated")
            for line, vals in zip(generated, wanted):
                line.write(vals)
            Line.create([
                dict(vals, move_id=move.id, is_generated=True)
                for vals in wanted[len(generated):]
            ])
            generated[len(wanted):].unlink()

    def _generated_line_vals(self):
        self.ensure_one()
        label = self.memo or self.ref or False
        if self.move_type in ("deposit", "payment"):
            if not self.bank_account_id:
                return []
            total = sum(self.item_line_ids.mapped("amount"))
            balance = total if self.move_type == "deposit" else -total
            return [{
                "account_id": self.bank_account_id.id,
                "partner_id": self.partner_id.id,
                "name": label,
                "amount": 0.0,
                **debit_credit(balance),
            }]
        if self.move_type == "transfer":
            if not (self.bank_account_id and self.dest_account_id):
                return []
            return [
                {
                    "account_id": self.dest_account_id.id,
                    "partner_id": False,
                    "name": label,
                    "amount": 0.0,
                    **debit_credit(self.amount),
                },
                {
                    "account_id": self.bank_account_id.id,
                    "partner_id": False,
                    "name": label,
                    "amount": 0.0,
                    **debit_credit(-self.amount),
                },
            ]
        return []

    # -------------------------------------------------------------------------
    # Checks
    # -------------------------------------------------------------------------

    def _check_draft(self):
        for move in self:
            if move.state == "posted":
                raise UserError(_(
                    "%s is posted and can't be changed. Reset it to draft first.",
                    move.display_name,
                ))

    def _check_lock_date(self):
        for move in self:
            lock_date = move.company_id.np_lock_date
            if lock_date and move.date <= lock_date:
                raise UserError(_(
                    "%(entry)s is dated %(date)s, which is on or before the "
                    "lock date (%(lock_date)s).",
                    entry=move.display_name,
                    date=format_date(self.env, move.date),
                    lock_date=format_date(self.env, lock_date),
                ))

    def _check_can_post(self):
        self.ensure_one()
        rounding = self.currency_id.rounding
        if self.move_type in ("deposit", "payment"):
            if not self.bank_account_id:
                raise ValidationError(_("Choose a bank account."))
            if not self.item_line_ids:
                raise ValidationError(_("Add at least one line."))
        elif self.move_type == "transfer":
            if not (self.bank_account_id and self.dest_account_id):
                raise ValidationError(_("Choose both the from and to accounts."))
            if self.bank_account_id == self.dest_account_id:
                raise ValidationError(_("The from and to accounts must be different."))
        else:
            if len(self.line_ids) < 2:
                raise ValidationError(_("A journal entry needs at least two lines."))
            for line in self.line_ids:
                if bool(line.debit) == bool(line.credit):
                    raise ValidationError(_(
                        "Each line needs either a debit or a credit (not both)."
                    ))

        if float_compare(self.amount_total, 0.0, precision_rounding=rounding) <= 0:
            raise ValidationError(_("The total must be greater than zero."))
        debit = sum(self.line_ids.mapped("debit"))
        credit = sum(self.line_ids.mapped("credit"))
        if not float_is_zero(debit - credit, precision_rounding=rounding):
            raise ValidationError(_(
                "The entry doesn't balance: debits %(debit)s, credits %(credit)s.",
                debit=debit,
                credit=credit,
            ))

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_post(self):
        for move in self.filtered(lambda m: m.state == "draft"):
            move._check_lock_date()
            move._sync_lines()
            try:
                move._check_can_post()
            except ValidationError as error:
                if len(self) == 1:
                    raise
                # When posting several at once, say which entry is the problem.
                raise ValidationError(_(
                    "%(entry)s: %(error)s",
                    entry=move.display_name,
                    error=error.args[0],
                )) from error
            vals = {"state": "posted"}
            if move.name == "/":
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    f"np.move.{move.move_type}",
                    sequence_date=move.date,
                )
            move.write(vals)
        return True

    def action_open_pay_wizard(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Pay %s", self.partner_id.name or _("Bill")),
            "res_model": "np.move.pay",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_move_id": self.id,
                "default_paid_date": self.bill_date or fields.Date.context_today(self),
                "default_bank_account_id": (
                    self.bank_account_id or self._default_pay_from_account()
                ).id,
                "default_check_number": self.check_number,
            },
        }

    def _default_pay_from_account(self):
        """Pay From for a bill: the account this vendor was last paid from,
        else the company default, else the only bank account (if just one)."""
        self.ensure_one()
        if self.partner_id:
            last_payment = self.search([
                ("move_type", "=", "payment"),
                ("state", "=", "posted"),
                ("partner_id", "=", self.partner_id.id),
                ("bank_account_id", "!=", False),
            ], order="date desc, id desc", limit=1)
            if last_payment:
                return last_payment.bank_account_id
        if self.company_id.np_default_payment_account_id:
            return self.company_id.np_default_payment_account_id
        bank_accounts = self.env["np.account"].search([("account_type", "=", "bank")], limit=2)
        return bank_accounts if len(bank_accounts) == 1 else bank_accounts.browse()

    def button_draft(self):
        if not self.env.user.has_group("nonprofit_accounting.group_np_bookkeeper"):
            raise AccessError(_("Only bookkeepers can reset entries to draft."))
        posted = self.filtered(lambda m: m.state == "posted")
        posted._check_lock_date()
        reconciled = posted.line_ids.filtered("reconciled")
        if reconciled:
            raise UserError(_(
                "%(entry)s is cleared on bank reconciliation %(reconciliation)s. "
                "Reopen that reconciliation first.",
                entry=reconciled[0].move_id.display_name,
                reconciliation=reconciled[0].reconciliation_id.display_name,
            ))
        posted.line_ids.filtered("reconciliation_id").write({
            "reconciliation_id": False,
            "rec_cleared": False,
        })
        posted.write({"state": "draft"})
        return True
