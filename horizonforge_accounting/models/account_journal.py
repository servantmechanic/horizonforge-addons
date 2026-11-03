from odoo import models
from odoo.exceptions import UserError
from odoo.tools.misc import format_datetime


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _hf_checks_to_print_domain(self):
        # Core's Checks to Print filter, plus checks already Paid: a payment
        # posted straight to the bank account skips In Process.
        return [
            ("journal_id", "in", self.ids),
            ("payment_method_line_id.code", "=", "check_printing"),
            ("state", "in", ("in_process", "paid")),
            ("is_sent", "=", False),
        ]

    def _get_journal_dashboard_data_batched(self):
        dashboard_data = super()._get_journal_dashboard_data_batched()
        # Core's own "N Checks to print" line reads num_checks_to_print, which
        # account_check_printing fills after the bank data; give it the same
        # queue as the Print Checks button.
        for journal_id, data in dashboard_data.items():
            if "hf_checks_to_print" in data:
                data["num_checks_to_print"] = data["hf_checks_to_print"]
        return dashboard_data

    def _fill_bank_cash_dashboard_data(self, dashboard_data):
        super()._fill_bank_cash_dashboard_data(dashboard_data)
        counts = dict(self.env["account.payment"]._read_group(
            self._hf_checks_to_print_domain(), ["journal_id"], ["__count"],
        ))
        for journal in self:
            dashboard_data[journal.id]["hf_checks_to_print"] = counts.get(journal, 0)
        for journal in self.filtered("online_bank_statement_provider_id"):
            provider = journal.online_bank_statement_provider_id.sudo()
            dashboard_data[journal.id]["hf_feed"] = {
                "last_sync": provider.last_successful_run
                and format_datetime(self.env, provider.last_successful_run, dt_format="short"),
                "error": provider.hf_last_error or False,
            }

    def action_hf_print_checks(self):
        """Print every check waiting in this journal's queue, in one batch."""
        self.ensure_one()
        payments = self.env["account.payment"].search(self._hf_checks_to_print_domain(), order="date, id")
        if not payments:
            raise UserError(self.env._("There are no checks to print."))
        return payments.print_checks()

    def action_checks_to_print(self):
        # Core's dashboard link: open the queue with its Check Amount column.
        return self.action_hf_open_checks_to_print()

    def action_hf_open_checks_to_print(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Checks to Print"),
            "res_model": "account.payment",
            "view_mode": "list,form",
            "domain": self._hf_checks_to_print_domain(),
            "context": {"create": False, "hf_checks_to_print": True},
        }

    def action_hf_sync_feed(self):
        self.ensure_one()
        self.online_bank_statement_provider_id.action_hf_sync_now()
        return {"type": "ir.actions.client", "tag": "soft_reload"}
