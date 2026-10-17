from odoo import Command
from odoo.tests import HttpCase, tagged

# Wait for a selector, fail after ~10s.
WAIT_FOR = """
const waitFor = (selector) => new Promise((resolve, reject) => {
    let tries = 0;
    const timer = setInterval(() => {
        const el = document.querySelector(selector);
        if (el) { clearInterval(timer); resolve(el); }
        else if (++tries > 100) { clearInterval(timer); reject(new Error("Not found: " + selector)); }
    }, 100);
});
"""


@tagged("post_install", "-at_install")
class TestNpUi(HttpCase):
    """Smoke tests: the main screens load in a real browser without errors."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.checking = cls.env.ref("nonprofit_accounting.np_account_1000")
        # Inside the period report's default range (last full month).
        period_start = cls.env["np.period.report"].new({}).date_from
        deposit = cls.env["np.move"].create({
            "move_type": "deposit",
            "date": period_start,
            "bank_account_id": cls.checking.id,
            "item_line_ids": [Command.create({
                "account_id": cls.env.ref("nonprofit_accounting.np_account_4010").id,
                "amount": 1000,
            })],
        })
        deposit.action_post()
        cls.reconciliation = cls.env["np.reconciliation"].create({
            "bank_account_id": cls.checking.id,
            "statement_date": period_start.replace(day=28),
            "statement_balance": 1000,
        })

    def _run(self, url, steps):
        code = WAIT_FOR + "(async () => {" + steps + "console.log('test successful'); })()" \
            ".catch((e) => console.error(e.message));"
        self.browser_js(url, code, login="admin")

    def test_dashboard(self):
        self._run("/odoo/action-nonprofit_accounting.np_dashboard_action", """
            await waitFor(".o_kanban_record button[name='action_reconcile']");
            await waitFor(".o_kanban_record button[name='action_new_deposit']");
        """)

    def test_deposit_form(self):
        self._run("/odoo/action-nonprofit_accounting.np_move_action_deposit/new", """
            await waitFor(".o_form_view .o_field_widget[name='bank_account_id']");
            await waitFor(".o_form_view .o_field_widget[name='item_line_ids']");
        """)

    def test_reconciliation_form(self):
        self._run(f"/odoo/action-nonprofit_accounting.np_reconciliation_action/{self.reconciliation.id}", """
            await waitFor(".o_field_widget[name='line_ids'] .o_data_row");
            const toggle = await waitFor(".o_field_widget[name='line_ids'] .o_data_row .o_boolean_toggle input");
            toggle.click();
            for (let i = 0; i < 50; i++) {
                const diff = document.querySelector(".o_field_widget[name='difference']").textContent;
                if (/0\\.00/.test(diff) && !/1,000/.test(diff)) { break; }
                await new Promise((r) => setTimeout(r, 100));
                if (i === 49) { throw new Error("Difference did not update: " + diff); }
            }
            (await waitFor(".o_form_button_save")).click();
            for (let i = 0; i < 50 && document.querySelector(".o_form_status_indicator_buttons:not(.invisible) .o_form_button_save"); i++) {
                await new Promise((r) => setTimeout(r, 100));
            }
        """)

    def test_reconciliation_saved(self):
        self.test_reconciliation_form()
        self.assertTrue(self.reconciliation.line_ids.rec_cleared, "toggle was saved")
        self.assertEqual(self.reconciliation.difference, 0.0)

    def test_period_report_click_through(self):
        self._run("/odoo/action-nonprofit_accounting.np_period_report_action", """
            (await waitFor(".modal button[name='action_view']")).click();
            const iframe = await waitFor("iframe.o_report_iframe, .o_action iframe");
            let link;
            for (let i = 0; i < 100 && !link; i++) {
                link = iframe.contentDocument && iframe.contentDocument.querySelector(".np-drill[data-np-kind='account']");
                if (!link) { await new Promise((r) => setTimeout(r, 100)); }
            }
            if (!link) { throw new Error("No drill-down link in report"); }
            link.click();
            (await waitFor(".o_list_view .o_data_row .o_data_cell")).click();
            await waitFor(".o_form_view .o_field_widget[name='item_line_ids']");
        """)
