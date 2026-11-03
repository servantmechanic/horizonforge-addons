from odoo.tests import HttpCase, tagged

# Passes only once the MIS report has rendered its table, so a missing action
# or a client error both fail.
WAIT_FOR_REPORT = """
    const deadline = Date.now() + 20000;
    (function check() {
        if (document.querySelector('.oe_mis_builder_content table')) {
            console.log('test successful');
        } else if (Date.now() > deadline) {
            console.error('The MIS report did not render');
        } else {
            setTimeout(check, 250);
        }
    })();
"""


@tagged("post_install", "-at_install")
class TestReportMenus(HttpCase):
    """Open each statement menu in a browser."""

    def _open(self, action_xmlid):
        self.browser_js(
            f"/odoo/action-horizonforge_accounting.{action_xmlid}",
            WAIT_FOR_REPORT,
            ready="odoo.isReady",
            login="admin",
            timeout=60,
        )

    def test_profit_and_loss(self):
        self._open("action_report_profit_loss")

    def test_profit_and_loss_monthly(self):
        self._open("action_report_profit_loss_monthly")

    def test_balance_sheet(self):
        self._open("action_report_balance_sheet")

    def test_missing_action_fails(self):
        with self.assertRaises(AssertionError):
            self._open("action_profit_loss")


# Passes once the action shows a view or a dialog, with no client error.
WAIT_FOR_ACTION = """
    const deadline = Date.now() + 20000;
    (function check() {
        if (document.querySelector('.modal-content, .o_view_controller')) {
            setTimeout(() => console.log('test successful'), 1000);
        } else if (Date.now() > deadline) {
            console.error('The action did not open');
        } else {
            setTimeout(check, 250);
        }
    })();
"""


@tagged("post_install", "-at_install")
class TestReportScreens(HttpCase):
    """Open the OCA report wizards and lists the statements sit beside."""

    def _open(self, action_xmlid):
        self.browser_js(f"/odoo/action-{action_xmlid}", WAIT_FOR_ACTION,
                        ready="odoo.isReady", login="admin", timeout=60)

    def test_general_ledger(self):
        self._open("account_financial_report.action_general_ledger_wizard")

    def test_trial_balance(self):
        self._open("account_financial_report.action_trial_balance_wizard")

    def test_aged_partner_balance(self):
        self._open("account_financial_report.action_aged_partner_balance_wizard")

    def test_mis_reports_list(self):
        self._open("mis_builder.mis_report_instance_view_action")
