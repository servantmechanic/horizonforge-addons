from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError
from odoo.tools.misc import format_date


class NpReconciliation(models.Model):
    _name = "np.reconciliation"
    _description = "Bank Reconciliation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "statement_date desc, id desc"

    bank_account_id = fields.Many2one(
        "np.account",
        string="Bank Account",
        required=True,
        domain=[("account_type", "=", "bank")],
        tracking=True,
    )
    statement_date = fields.Date(
        required=True,
        tracking=True,
        help="The ending date on the bank statement.",
    )
    statement_balance = fields.Monetary(
        string="Statement Ending Balance",
        currency_field="currency_id",
        tracking=True,
    )
    state = fields.Selection(
        [("draft", "In Progress"), ("done", "Reconciled")],
        string="Status",
        default="draft",
        required=True,
        readonly=True,
        copy=False,
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    previous_id = fields.Many2one(
        "np.reconciliation",
        string="Previous Reconciliation",
        compute="_compute_previous_id",
    )
    beginning_balance = fields.Monetary(
        compute="_compute_previous_id",
        currency_field="currency_id",
        help="The ending balance of the previous reconciliation (zero for the first one).",
    )
    line_ids = fields.One2many(
        "np.move.line",
        "reconciliation_id",
        string="Transactions",
    )
    cleared_deposits = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    cleared_payments = fields.Monetary(compute="_compute_totals", currency_field="currency_id")
    cleared_balance = fields.Monetary(
        compute="_compute_totals",
        currency_field="currency_id",
        help="Beginning balance + cleared deposits − cleared payments.",
    )
    difference = fields.Monetary(
        compute="_compute_totals",
        currency_field="currency_id",
        help="Statement ending balance − cleared balance. Must be zero to finish.",
    )
    statement_file = fields.Binary(string="Statement", attachment=True, copy=False)
    statement_filename = fields.Char()
    note = fields.Text()

    @api.depends("bank_account_id", "statement_date")
    def _compute_display_name(self):
        for rec in self:
            if rec.bank_account_id and rec.statement_date:
                rec.display_name = f"{rec.bank_account_id.name} · {format_date(self.env, rec.statement_date)}"
            else:
                rec.display_name = _("New Reconciliation")

    @api.depends("bank_account_id", "statement_date")
    def _compute_previous_id(self):
        for rec in self:
            previous = self.browse()
            if rec.bank_account_id and rec.statement_date:
                previous = self.search([
                    ("bank_account_id", "=", rec.bank_account_id.id),
                    ("state", "=", "done"),
                    ("statement_date", "<", rec.statement_date),
                    ("id", "!=", rec._origin.id or 0),
                ], order="statement_date desc, id desc", limit=1)
            rec.previous_id = previous
            rec.beginning_balance = previous.statement_balance

    @api.depends("beginning_balance", "statement_balance", "line_ids.rec_cleared",
                 "line_ids.debit", "line_ids.credit")
    def _compute_totals(self):
        for rec in self:
            cleared = rec.line_ids.filtered("rec_cleared")
            rec.cleared_deposits = sum(cleared.mapped("debit"))
            rec.cleared_payments = sum(cleared.mapped("credit"))
            rec.cleared_balance = rec.beginning_balance + rec.cleared_deposits - rec.cleared_payments
            rec.difference = rec.currency_id.round(rec.statement_balance - rec.cleared_balance)

    @api.constrains("bank_account_id", "state")
    def _check_one_in_progress(self):
        for rec in self.filtered(lambda r: r.state == "draft"):
            if self.search_count([
                ("bank_account_id", "=", rec.bank_account_id.id),
                ("state", "=", "draft"),
                ("id", "!=", rec.id),
            ]):
                raise ValidationError(_(
                    "%s already has a reconciliation in progress. Finish or delete it first.",
                    rec.bank_account_id.display_name,
                ))

    @api.constrains("bank_account_id", "statement_date")
    def _check_statement_date(self):
        for rec in self:
            later = self.search([
                ("bank_account_id", "=", rec.bank_account_id.id),
                ("state", "=", "done"),
                ("statement_date", ">=", rec.statement_date),
                ("id", "!=", rec.id),
            ], limit=1)
            if later:
                raise ValidationError(_(
                    "The statement date must be after the last reconciliation (%s).",
                    later.display_name,
                ))

    # -------------------------------------------------------------------------
    # CRUD
    # -------------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs.action_refresh()
        return recs

    def write(self, vals):
        if vals.keys() & {"bank_account_id", "statement_date"}:
            for rec in self:
                if rec.state == "done":
                    raise UserError(_("Reopen the reconciliation before changing it."))
        res = super().write(vals)
        if vals.keys() & {"bank_account_id", "statement_date"}:
            self.action_refresh()
        return res

    @api.ondelete(at_uninstall=False)
    def _unlink_only_in_progress(self):
        if any(rec.state == "done" for rec in self):
            raise UserError(_("Reopen the reconciliation before deleting it."))

    def unlink(self):
        self.line_ids.write({"reconciliation_id": False, "rec_cleared": False})
        return super().unlink()

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def _candidate_line_domain(self):
        self.ensure_one()
        return [
            ("account_id", "=", self.bank_account_id.id),
            ("state", "=", "posted"),
            ("date", "<=", self.statement_date),
            ("reconciliation_id", "=", False),
        ]

    def action_refresh(self):
        """Load uncleared posted transactions up to the statement date, and
        drop ones that no longer belong (other account, later date)."""
        Line = self.env["np.move.line"]
        for rec in self.filtered(lambda r: r.state == "draft"):
            stale = rec.line_ids.filtered(lambda line: (
                line.account_id != rec.bank_account_id
                or line.date > rec.statement_date
                or line.state != "posted"
            ))
            stale.write({"reconciliation_id": False, "rec_cleared": False})
            Line.search(rec._candidate_line_domain()).write({"reconciliation_id": rec.id})
        return True

    def action_clear_all(self):
        self.line_ids.write({"rec_cleared": True})
        return True

    def action_finish(self):
        for rec in self:
            if rec.state != "draft":
                continue
            if not rec.currency_id.is_zero(rec.difference):
                raise UserError(_(
                    "The difference must be zero to finish. It is %(difference)s.",
                    difference=rec.difference,
                ))
            rec.line_ids.filtered(lambda line: not line.rec_cleared).write({"reconciliation_id": False})
            rec.state = "done"
        return True

    def action_reopen(self):
        for rec in self:
            later = self.search([
                ("bank_account_id", "=", rec.bank_account_id.id),
                ("state", "=", "done"),
                ("statement_date", ">", rec.statement_date),
            ], limit=1)
            if later:
                raise UserError(_(
                    "Only the most recent reconciliation can be reopened. Reopen %s first.",
                    later.display_name,
                ))
            rec.state = "draft"
            rec.action_refresh()
        return True
