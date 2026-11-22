import base64
import calendar
from collections import defaultdict

from markupsafe import Markup, escape

from odoo import api, fields, models
from odoo.exceptions import UserError
from odoo.fields import Command
from odoo.tools import float_is_zero, format_amount

from . import qb_parse

# QuickBooks account type -> Odoo account type
QB_TYPES = {
    "bank": "asset_cash",
    "accounts receivable (a/r)": "asset_receivable",
    "accounts receivable": "asset_receivable",
    "other current assets": "asset_current",
    "other current asset": "asset_current",
    "fixed assets": "asset_fixed",
    "fixed asset": "asset_fixed",
    "other assets": "asset_non_current",
    "other asset": "asset_non_current",
    "accounts payable (a/p)": "liability_payable",
    "accounts payable": "liability_payable",
    "credit card": "liability_credit_card",
    "other current liabilities": "liability_current",
    "other current liability": "liability_current",
    "long term liabilities": "liability_non_current",
    "long term liability": "liability_non_current",
    "equity": "equity",
    "income": "income",
    "other income": "income_other",
    "cost of goods sold": "expense_direct_cost",
    "expenses": "expense",
    "expense": "expense",
    "other expense": "expense",
    "other expenses": "expense",
}

# Where new accounts of each type are numbered from (padded to the chart's
# code length), stepping by 100 on a 6-digit chart.
CODE_START = {
    "asset_cash": "1012",
    "asset_receivable": "1210",
    "asset_current": "1120",
    "asset_prepayments": "1420",
    "asset_fixed": "1530",
    "asset_non_current": "1920",
    "liability_payable": "2110",
    "liability_credit_card": "2020",
    "liability_current": "2120",
    "liability_non_current": "2920",
    "equity": "3100",
    "equity_unaffected": "3900",
    "income": "4100",
    "income_other": "4600",
    "expense_direct_cost": "5600",
    "expense": "6400",
    "expense_depreciation": "6810",
    "clearing": "1990",
}

INCOME_TYPES = ("income", "income_other")
PL_TYPES = ("income", "income_other", "expense", "expense_depreciation", "expense_direct_cost")


def _account_type_selection(self):
    return self.env["account.account"]._fields["account_type"].selection


class HfQbImport(models.TransientModel):
    _name = "hf.qb.import"
    _description = "Import from QuickBooks Online"

    state = fields.Selection(
        [("upload", "Upload"), ("map", "Map Accounts"), ("done", "Done")],
        default="upload",
    )
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company)
    currency_id = fields.Many2one(related="company_id.currency_id")
    cutover_date = fields.Date(
        string="Opening Balance Date",
        required=True,
        help="The date of the QuickBooks Trial Balance, usually the last day of a "
             "month or year. Opening balances and open invoices are dated this day, "
             "and new transactions go in Odoo from the day after.",
    )
    account_list_file = fields.Binary(string="Account List", required=True)
    account_list_filename = fields.Char()
    trial_balance_file = fields.Binary(string="Trial Balance", required=True)
    trial_balance_filename = fields.Char()
    ar_aging_file = fields.Binary(string="A/R Aging Detail")
    ar_aging_filename = fields.Char()
    ap_aging_file = fields.Binary(string="A/P Aging Detail")
    ap_aging_filename = fields.Char()
    customers_file = fields.Binary(string="Customer Contact List")
    customers_filename = fields.Char()
    vendors_file = fields.Binary(string="Vendor Contact List")
    vendors_filename = fields.Char()
    pl_history_file = fields.Binary(
        string="Profit and Loss by Month",
        help="Optional. Monthly income and expense history before the opening "
             "balance date, for comparisons with past years. It should cover at "
             "least the fiscal year up to that date.",
    )
    pl_history_filename = fields.Char()
    create_bank_journals = fields.Boolean(
        default=True,
        help="Create a bank journal for each new Bank or Credit Card account, so it "
             "can be reconciled and connected to a bank feed.",
    )
    line_ids = fields.One2many("hf.qb.import.account", "wizard_id", string="Accounts")
    summary = fields.Html(readonly=True)
    result = fields.Html(readonly=True)
    move_ids = fields.Many2many("account.move", string="Created Entries", readonly=True)

    # ------------------------------------------------------------------
    # Reading the files
    # ------------------------------------------------------------------

    def _rows(self, fname):
        data = self[fname]
        if not data:
            return None
        try:
            return qb_parse.read_rows(base64.b64decode(data), self[fname.replace("_file", "_filename")])
        except Exception as e:  # noqa: BLE001 - any unreadable file
            raise UserError(self.env._("%(file)s can't be read: %(error)s",
                                       file=self._fields[fname].string, error=e)) from e

    def _parse(self, fname, parser, *args):
        rows = self._rows(fname)
        if rows is None:
            return []
        try:
            return parser(rows, *args)
        except qb_parse.QbParseError as e:
            raise UserError(self.env._("%(file)s: %(error)s",
                                       file=self._fields[fname].string, error=e)) from e

    def _read_files(self):
        return {
            "accounts": self._parse("account_list_file", qb_parse.parse_account_list),
            "trial_balance": self._parse("trial_balance_file", qb_parse.parse_trial_balance),
            "ar": self._parse("ar_aging_file", qb_parse.parse_aging, ["customer", "name"]),
            "ap": self._parse("ap_aging_file", qb_parse.parse_aging, ["vendor", "supplier", "name"]),
            "customers": self._parse("customers_file", qb_parse.parse_contacts, ["customer", "name"]),
            "vendors": self._parse("vendors_file", qb_parse.parse_contacts, ["vendor", "supplier", "name"]),
            "history": self._parse("pl_history_file", qb_parse.parse_pl_by_month),
        }

    # ------------------------------------------------------------------
    # Step 1: analyze and propose a mapping
    # ------------------------------------------------------------------

    def _company_accounts(self):
        Account = self.env["account.account"].with_company(self.company_id)
        return Account.search(Account._check_company_domain(self.company_id))

    def _default_partner_account(self, fname):
        partner = self.env["res.partner"].with_company(self.company_id).new({})
        return partner[fname]

    def _next_code(self, account_type, used):
        sample = self._company_accounts()[:1]
        digits = len(sample.code) if sample else 6
        step = 10 ** max(digits - 4, 0)
        code = int(CODE_START.get(account_type, "9000").ljust(digits, "0"))
        while str(code) in used:
            code += step
        used.add(str(code))
        return str(code)

    def action_analyze(self):
        self.ensure_one()
        data = self._read_files()
        if not data["accounts"]:
            raise UserError(self.env._("The Account List has no accounts."))
        self.line_ids.unlink()
        accounts = {acc["name"]: acc for acc in data["accounts"]}
        balances = defaultdict(float)
        for line in data["trial_balance"]:
            balances[line["name"]] += line["balance"]
        leaf_names = defaultdict(list)
        for name in accounts:
            leaf_names[name.split(":")[-1].strip().lower()].append(name)
        history = defaultdict(float)
        for row in data["history"]:
            name = row["name"]
            if name not in accounts and len(leaf_names.get(name.lower(), [])) == 1:
                name = leaf_names[name.lower()][0]
            history[name] += row["amount"]
        # Accounts only in the trial balance or history still need a mapping.
        for name in list(balances) + list(history):
            accounts.setdefault(name, {"name": name, "type": "", "detail_type": "", "number": ""})

        existing = {acc.name.lower(): acc for acc in self._company_accounts()}
        used_codes = set(self._company_accounts().mapped("code"))
        receivable = self._default_partner_account("property_account_receivable_id")
        payable = self._default_partner_account("property_account_payable_id")
        retained = self.company_id.get_unaffected_earnings_account()
        leaf_counts = defaultdict(int)
        for name in accounts:
            leaf_counts[name.split(":")[-1].strip().lower()] += 1

        lines = []
        for sequence, (name, acc) in enumerate(accounts.items()):
            account_type = QB_TYPES.get(acc["type"].strip().lower())
            detail = acc["detail_type"].strip().lower()
            if account_type == "expense" and "depreciation" in detail:
                account_type = "expense_depreciation"
            role = "normal"
            if account_type == "asset_receivable":
                role = "receivable"
            elif account_type == "liability_payable":
                role = "payable"
            elif account_type == "equity" and ("retained earnings" in detail or name.lower() == "retained earnings"):
                role = "retained"
            leaf = name.split(":")[-1].strip()
            vals = {
                "wizard_id": self.id,
                "sequence": sequence,
                "qb_name": name,
                "qb_type": acc["type"],
                "qb_detail_type": acc["detail_type"],
                "qb_number": acc["number"],
                "role": role,
                "balance": balances.get(name, 0.0),
                "history_total": history.get(name, 0.0),
                "new_name": leaf if leaf_counts[leaf.lower()] == 1 else name.replace(":", " - "),
                "new_account_type": account_type,
            }
            match = {
                "receivable": receivable, "payable": payable, "retained": retained,
            }.get(role) or existing.get(name.lower()) or existing.get(leaf.lower())
            if match:
                vals.update(action="map", account_id=match.id)
            elif account_type:
                code = acc["number"] if acc["number"] and acc["number"] not in used_codes else None
                if code:
                    used_codes.add(code)
                vals.update(action="create", new_code=code or self._next_code(account_type, used_codes))
            else:
                vals.update(action="map")
            lines.append(vals)
        self.env["hf.qb.import.account"].create(lines)
        self.summary = self._summary_html(data)
        self.state = "map"
        return self._reopen()

    def _summary_html(self, data):
        def money(amount):
            return format_amount(self.env, amount, self.currency_id)

        tb_debit = sum(line["balance"] for line in data["trial_balance"] if line["balance"] > 0)
        tb_credit = -sum(line["balance"] for line in data["trial_balance"] if line["balance"] < 0)
        rows = [
            (self.env._("Accounts in QuickBooks"), len(self.line_ids)),
            (self.env._("Accounts to create"), len(self.line_ids.filtered(lambda l: l.action == "create"))),
            (self.env._("Trial balance debits / credits"), f"{money(tb_debit)} / {money(tb_credit)}"),
        ]
        warnings = []
        if not float_is_zero(tb_debit - tb_credit, precision_rounding=self.currency_id.rounding):
            warnings.append(self.env._("The trial balance doesn't balance."))
        for role, key, label in (("receivable", "ar", "A/R"), ("payable", "ap", "A/P")):
            tb_total = sum(self.line_ids.filtered(lambda l, r=role: l.role == r).mapped("balance"))
            aging_total = sum(entry["open_balance"] for entry in data[key])
            if role == "payable":
                tb_total = -tb_total
            rows.append((self.env._("%(label)s open items", label=label),
                         f"{len(data[key])}, {money(aging_total)}"))
            if not float_is_zero(tb_total - aging_total, precision_rounding=self.currency_id.rounding):
                warnings.append(self.env._(
                    "%(label)s aging (%(aging)s) differs from the trial balance (%(tb)s). The "
                    "difference stays in Opening Balance Clearing.",
                    label=label, aging=money(aging_total), tb=money(tb_total),
                ))
        if data["history"]:
            months = sorted({row["month"] for row in data["history"]})
            rows.append((self.env._("History months"), f"{months[0]:%b %Y} to {months[-1]:%b %Y}"))
            if months[-1] > self.cutover_date:
                warnings.append(self.env._("History after the opening balance date is left out."))
            fy_start = self.company_id.compute_fiscalyear_dates(self.cutover_date)["date_from"]
            if months[0] > fy_start:
                warnings.append(self.env._(
                    "History starts after the fiscal year does (%(start)s), so this year's "
                    "income and expenses will be incomplete.", start=fy_start,
                ))
        unmapped = self.line_ids.filtered(lambda l: not l.new_account_type and not l.account_id)
        if unmapped:
            warnings.append(self.env._(
                "Not in the Account List, choose an account for: %(names)s",
                names=", ".join(unmapped.mapped("qb_name")),
            ))
        html = Markup("<table class='table table-sm w-auto'>")
        for label, value in rows:
            html += Markup("<tr><td>%s</td><td class='text-end'>%s</td></tr>") % (label, value)
        html += Markup("</table>")
        for warning in warnings:
            html += Markup("<p class='text-warning'>%s</p>") % warning
        return html

    def _reopen(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def action_back(self):
        self.state = "upload"
        return self._reopen()

    # ------------------------------------------------------------------
    # Step 2: import
    # ------------------------------------------------------------------

    def _xmlid(self, key):
        return f"horizonforge_accounting.{self.company_id.id}_{key}"

    def _clearing_account(self):
        account = self.env.ref(self._xmlid("qb_clearing"), raise_if_not_found=False)
        if account:
            return account
        used = set(self._company_accounts().mapped("code"))
        account = self.env["account.account"].create({
            "code": self._next_code("clearing", used),
            "name": self.env._("Opening Balance Clearing"),
            "account_type": "asset_current",
            "company_ids": [Command.set(self.company_id.ids)],
        })
        self.env["ir.model.data"]._update_xmlids([{
            "xml_id": self._xmlid("qb_clearing"), "record": account, "noupdate": True,
        }])
        return account

    def _create_accounts(self):
        Journal = self.env["account.journal"].with_company(self.company_id)
        used_journal_codes = set(Journal.with_context(active_test=False).search(
            Journal._check_company_domain(self.company_id)).mapped("code"))
        for line in self.line_ids.filtered(lambda l: l.action == "create"):
            if not line.new_code or not line.new_name or not line.new_account_type:
                raise UserError(self.env._("Give %(name)s a code, name and type.", name=line.qb_name))
            account = self.env["account.account"].create({
                "code": line.new_code,
                "name": line.new_name,
                "account_type": line.new_account_type,
                "company_ids": [Command.set(self.company_id.ids)],
            })
            line.write({"action": "map", "account_id": account.id})
            if self.create_bank_journals and line.new_account_type in ("asset_cash", "liability_credit_card"):
                base = "".join(ch for ch in line.new_name.upper() if ch.isalnum())[:4] or "BNK"
                code, n = base, 1
                while code in used_journal_codes:
                    n += 1
                    code = f"{base[:4 - len(str(n))]}{n}"
                used_journal_codes.add(code)
                Journal.create({
                    "name": line.new_name,
                    "code": code,
                    "type": "bank",
                    "default_account_id": account.id,
                    "company_id": self.company_id.id,
                })

    def _partner(self, name, rank_field, contact=None, cache=None):
        key = name.strip().lower()
        if key in cache:
            partner = cache[key]
        else:
            partner = self.env["res.partner"].search([
                ("name", "=ilike", name.strip()),
                ("parent_id", "=", False),
                "|", ("company_id", "=", False), ("company_id", "=", self.company_id.id),
            ], limit=1)
            if not partner:
                partner = self.env["res.partner"].create({
                    "name": name.strip(),
                    "is_company": True,
                    "email": (contact or {}).get("email") or False,
                    "phone": (contact or {}).get("phone") or False,
                })
            cache[key] = partner
        if not partner[rank_field]:
            partner[rank_field] = 1
        return partner

    def _misc_journal(self):
        journal = self.env["account.journal"].search([
            *self.env["account.journal"]._check_company_domain(self.company_id),
            ("type", "=", "general"),
        ], limit=1)
        if not journal:
            raise UserError(self.env._("The company needs a Miscellaneous journal."))
        return journal

    def _entry(self, date, ref, balances, clearing):
        """Post an entry with {account: balance} lines, balanced on clearing."""
        rounding = self.currency_id.rounding
        lines = [(account, balance) for account, balance in balances.items()
                 if not float_is_zero(balance, precision_rounding=rounding)]
        rest = -sum(balance for _account, balance in lines)
        if not float_is_zero(rest, precision_rounding=rounding):
            lines.append((clearing, rest))
        if not lines:
            return self.env["account.move"]
        move = self.env["account.move"].create({
            "move_type": "entry",
            "date": date,
            "ref": ref,
            "journal_id": self._misc_journal().id,
            "company_id": self.company_id.id,
            "line_ids": [Command.create({
                "account_id": account.id,
                "name": ref,
                "debit": max(balance, 0.0),
                "credit": max(-balance, 0.0),
            }) for account, balance in lines],
        })
        move.action_post()
        return move

    def _history_entries(self, data, clearing):
        by_name = {line.qb_name: line for line in self.line_ids}
        leaf = defaultdict(list)
        for line in self.line_ids:
            leaf[line.qb_name.split(":")[-1].strip().lower()].append(line)
        months = defaultdict(lambda: defaultdict(float))
        for row in data["history"]:
            if row["month"] > self.cutover_date:
                continue
            line = by_name.get(row["name"]) or (leaf.get(row["name"].lower()) or [None])[0]
            account = line.account_id if line else None
            if not account:
                continue
            sign = -1 if account.account_type in INCOME_TYPES else 1
            months[row["month"]][account] += sign * row["amount"]
        moves = self.env["account.move"]
        history_total = 0.0
        for month in sorted(months):
            last_day = month.replace(day=calendar.monthrange(month.year, month.month)[1])
            balances = months[month]
            history_total += sum(balances.values())
            moves |= self._entry(
                min(last_day, self.cutover_date),
                self.env._("QuickBooks history %(month)s", month=f"{month:%b %Y}"),
                balances,
                clearing,
            )
        return moves, history_total

    def _opening_entry(self, history_total, clearing):
        has_history = bool(self.pl_history_file)
        retained = self.company_id.get_unaffected_earnings_account()
        balances = defaultdict(float)
        for line in self.line_ids.filtered(lambda l: l.balance):
            account = line.account_id
            if not account:
                raise UserError(self.env._("Choose an account for %(name)s.", name=line.qb_name))
            if line.role in ("receivable", "payable"):
                # Replaced by the open invoices and bills, against clearing.
                balances[clearing] += line.balance
            elif has_history and (account.account_type in PL_TYPES or line.role == "retained"):
                # The history entries carry income and expenses; what they
                # don't cover is earnings from before the history starts.
                balances[retained] += line.balance
            else:
                balances[account] += line.balance
        if has_history:
            balances[retained] -= history_total
        return self._entry(self.cutover_date, self.env._("QuickBooks opening balances"), balances, clearing)

    def _open_items(self, entries, partner_type, clearing, contacts):
        cache = {}
        moves = self.env["account.move"]
        for entry in entries:
            amount = entry["open_balance"]
            if partner_type == "customer":
                move_type = "out_invoice" if amount > 0 else "out_refund"
                partner = self._partner(entry["partner"], "customer_rank", contacts.get(entry["partner"].lower()), cache)
            else:
                move_type = "in_invoice" if amount > 0 else "in_refund"
                partner = self._partner(entry["partner"], "supplier_rank", contacts.get(entry["partner"].lower()), cache)
            label = " ".join(filter(None, [
                "QuickBooks", entry["type"], entry["number"], self.env._("of %s", entry["date"].strftime("%m/%d/%Y")),
            ]))
            move = self.env["account.move"].with_company(self.company_id).create({
                "move_type": move_type,
                "partner_id": partner.id,
                "invoice_date": entry["date"],
                "date": self.cutover_date,
                "invoice_date_due": entry["due_date"],
                "ref": entry["number"] or False,
                "invoice_line_ids": [Command.create({
                    "name": label,
                    "account_id": clearing.id,
                    "quantity": 1,
                    "price_unit": abs(amount),
                    "tax_ids": [Command.clear()],
                })],
            })
            move.action_post()
            moves |= move
        return moves

    def action_import(self):
        self.ensure_one()
        if self.env.ref(self._xmlid("qb_opening_move"), raise_if_not_found=False):
            raise UserError(self.env._(
                "QuickBooks balances were already imported for this company. Reverse or "
                "delete that opening entry first."
            ))
        data = self._read_files()
        self._create_accounts()
        clearing = self._clearing_account()
        contacts = {}
        for contact in data["customers"] + data["vendors"]:
            contacts.setdefault(contact["name"].lower(), contact)
        cache = {}
        for contact in data["customers"]:
            self._partner(contact["name"], "customer_rank", contact, cache)
        for contact in data["vendors"]:
            self._partner(contact["name"], "supplier_rank", contact, cache)

        history_moves, history_total = self._history_entries(data, clearing)
        opening = self._opening_entry(history_total, clearing)
        if opening:
            self.env["ir.model.data"]._update_xmlids([{
                "xml_id": self._xmlid("qb_opening_move"), "record": opening, "noupdate": True,
            }])
        invoices = self._open_items(data["ar"], "customer", clearing, contacts)
        bills = self._open_items(data["ap"], "vendor", clearing, contacts)
        self.move_ids = history_moves | opening | invoices | bills
        self.result = self._result_html(clearing, opening, invoices, bills, history_moves)
        self.state = "done"
        return self._reopen()

    def _result_html(self, clearing, opening, invoices, bills, history_moves):
        lines = self.env["account.move.line"].search([
            ("account_id", "=", clearing.id), ("parent_state", "=", "posted"),
        ])
        left = sum(lines.mapped("balance"))
        money = format_amount(self.env, left, self.currency_id)
        html = Markup("<ul>")
        for label, count in (
            (self.env._("Opening balance entry"), len(opening)),
            (self.env._("Open invoices and credit notes"), len(invoices)),
            (self.env._("Open bills and vendor credits"), len(bills)),
            (self.env._("Monthly history entries"), len(history_moves)),
        ):
            html += Markup("<li>%s: %s</li>") % (label, count)
        html += Markup("</ul>")
        if float_is_zero(left, precision_rounding=self.currency_id.rounding):
            html += Markup("<p class='text-success'>%s</p>") % self.env._(
                "Opening Balance Clearing is zero: the import ties out to the trial balance.")
        else:
            html += Markup("<p class='text-danger'>%s</p>") % self.env._(
                "Opening Balance Clearing is %(amount)s, not zero. Compare the aging reports "
                "with the A/R and A/P balances in the trial balance, then fix it with a journal "
                "entry.", amount=money)
        return html

    def action_open_moves(self):
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Imported Entries"),
            "res_model": "account.move",
            "view_mode": "list,form",
            "domain": [("id", "in", self.move_ids.ids)],
        }


class HfQbImportAccount(models.TransientModel):
    _name = "hf.qb.import.account"
    _description = "QuickBooks account mapping"
    _order = "sequence, id"

    wizard_id = fields.Many2one("hf.qb.import", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="wizard_id.company_id")
    currency_id = fields.Many2one(related="wizard_id.currency_id")
    sequence = fields.Integer()
    qb_name = fields.Char(string="QuickBooks Account", readonly=True)
    qb_type = fields.Char(string="QuickBooks Type", readonly=True)
    qb_detail_type = fields.Char(string="Detail Type", readonly=True)
    qb_number = fields.Char(string="QuickBooks Number", readonly=True)
    role = fields.Selection(
        [
            ("normal", "Normal"),
            ("receivable", "Receivable"),
            ("payable", "Payable"),
            ("retained", "Retained Earnings"),
        ],
        default="normal",
        readonly=True,
    )
    balance = fields.Monetary(
        string="Opening Balance",
        readonly=True,
        help="Debit minus credit in the trial balance.",
    )
    history_total = fields.Monetary(string="History Total", readonly=True)
    action = fields.Selection(
        [("map", "Use Existing"), ("create", "Create")],
        required=True,
        default="create",
    )
    account_id = fields.Many2one(
        "account.account",
        string="Odoo Account",
        domain="[('company_ids', 'in', company_id)]",
    )
    new_code = fields.Char(string="New Code")
    new_name = fields.Char(string="New Name")
    new_account_type = fields.Selection(selection=_account_type_selection, string="New Type")

    @api.onchange("account_id")
    def _onchange_account_id(self):
        if self.account_id:
            self.action = "map"
