from odoo import models
from odoo.tools.misc import format_datetime


class AccountJournal(models.Model):
    _inherit = "account.journal"

    def _fill_bank_cash_dashboard_data(self, dashboard_data):
        super()._fill_bank_cash_dashboard_data(dashboard_data)
        for journal in self.filtered("online_bank_statement_provider_id"):
            provider = journal.online_bank_statement_provider_id.sudo()
            dashboard_data[journal.id]["hf_feed"] = {
                "last_sync": provider.last_successful_run
                and format_datetime(self.env, provider.last_successful_run, dt_format="short"),
                "error": provider.hf_last_error or False,
            }

    def action_hf_sync_feed(self):
        self.ensure_one()
        self.online_bank_statement_provider_id.action_hf_sync_now()
        return {"type": "ir.actions.client", "tag": "soft_reload"}
