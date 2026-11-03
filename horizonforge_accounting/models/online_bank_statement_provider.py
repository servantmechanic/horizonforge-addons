from odoo import fields, models


class OnlineBankStatementProvider(models.Model):
    _inherit = "online.bank.statement.provider"

    hf_last_error = fields.Text(
        string="Last Sync Error",
        readonly=True,
        copy=False,
        help="Why the last scheduled pull failed. Cleared by the next one that works.",
    )

    def _log_provider_exception(self, exception, statement_date_since, statement_date_until):
        res = super()._log_provider_exception(exception, statement_date_since, statement_date_until)
        self.sudo().hf_last_error = str(exception) or self.env._("Unknown error")
        return res

    def _schedule_next_run(self, failed_since=None):
        res = super()._schedule_next_run(failed_since=failed_since)
        if not failed_since:
            self.sudo().hf_last_error = False
        return res

    def action_hf_sync_now(self):
        """Pull from the last successful pull up to now, showing any error."""
        now = fields.Datetime.now()
        for provider in self:
            since = provider.last_successful_run or fields.Datetime.subtract(now, days=30)
            provider.with_context(plaid_lookback=True)._pull(since, now)
            provider.sudo().write({"last_successful_run": now, "hf_last_error": False})
