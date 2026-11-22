from odoo.tests import HttpCase, tagged

from odoo.addons.horizonforge_accounting.tests.test_ui import WAIT_FOR_ACTION


@tagged("post_install", "-at_install")
class TestJobScreens(HttpCase):
    def _open(self, action_xmlid):
        self.browser_js(f"/odoo/action-horizonforge_job_accounting.{action_xmlid}", WAIT_FOR_ACTION,
                        ready="odoo.isReady", login="admin", timeout=60)

    def test_job_profitability(self):
        self._open("action_hf_job_profitability")

    def test_job_costs_and_revenue(self):
        self._open("action_hf_job_profit_line")
