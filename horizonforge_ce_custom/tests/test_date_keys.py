from odoo.tests import HttpCase, tagged

WAIT_FOR = """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waitFor = async (check, what) => {
    for (let i = 0; i < 100; i++) {
        const found = typeof check === "string" ? document.querySelector(check) : check();
        if (found) { return found; }
        await sleep(100);
    }
    throw new Error("Timed out: " + (what || check));
};
"""


@tagged("post_install", "-at_install")
class TestDateKeys(HttpCase):

    def test_plus_minus_on_date_field(self):
        """+ and - move a date field a day; a date being typed is left alone."""
        cron = self.env["ir.cron"].search([], limit=1)
        cron.nextcall = "2030-03-10 08:00:00"
        code = WAIT_FOR + """(async () => {
            const input = () => document.querySelector(".o_field_widget[name='nextcall'] .o_input");
            await waitFor(input, "date field");
            input().focus();
            await sleep(100);
            const key = (k) => input().dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true }));
            const shows = (day) => input().value.includes("03/" + day + "/2030");
            key("+");
            await waitFor(() => shows("11"), "+ moves a day later");
            key("-");
            await sleep(100);
            key("-");
            await waitFor(() => shows("09"), "- moves a day earlier");
            // Mid-typing, - is a character, not a step.
            input().value = "03/0";
            const typed = !input().dispatchEvent(new KeyboardEvent("keydown", { key: "-", bubbles: true, cancelable: true }));
            if (typed) { throw new Error("- was taken while typing"); }
            (await waitFor(".o_form_button_cancel")).click();
            await sleep(300);
            console.log("test successful");
        })().catch((e) => console.error(e.message));"""
        self.browser_js(f"/odoo/action-base.ir_cron_act/{cron.id}", code, login="admin")
