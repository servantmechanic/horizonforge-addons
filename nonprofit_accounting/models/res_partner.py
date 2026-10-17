from odoo import _, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    np_income_account_id = fields.Many2one(
        "np.account",
        string="Default Income Account",
        domain=[("account_type", "=", "income")],
        help="Pre-filled on new deposit lines when this contact is Received From.",
    )
    np_expense_account_id = fields.Many2one(
        "np.account",
        string="Default Expense Account",
        domain=[("account_type", "=", "expense")],
        help="Pre-filled on new bill lines when this contact is Paid To.",
    )
    np_entry_count = fields.Integer(
        compute="_compute_np_entry_count",
        groups="nonprofit_accounting.group_np_viewer",
    )

    def _compute_np_entry_count(self):
        counts = dict(self.env["np.move"]._read_group(
            [("partner_id", "in", self.ids)], ["partner_id"], ["__count"],
        ))
        for partner in self:
            partner.np_entry_count = counts.get(partner, 0)

    def action_np_open_entries(self):
        self.ensure_one()
        action = self.env["ir.actions.act_window"]._for_xml_id(
            "nonprofit_accounting.np_move_action_all"
        )
        action["name"] = _("Transactions: %s", self.display_name)
        action["domain"] = [("partner_id", "=", self.id)]
        return action
