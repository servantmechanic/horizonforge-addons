from odoo.tests import HttpCase, new_test_user, tagged
from odoo.tests.common import JsonRpcException

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
class TestQuickCreate(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = new_test_user(
            cls.env, login="hf_clerk", groups="base.group_user,base.group_partner_manager",
        )

    def _name_create(self, login, model, name):
        self.authenticate(login, login)
        return self.make_jsonrpc_request("/web/dataset/call_kw", {
            "model": model, "method": "name_create", "args": [name], "kwargs": {},
        })

    def _partner_exists(self, name):
        return bool(self.env["res.partner"].search_count([("name", "=", name)]))

    def test_blocked_by_default(self):
        self.assertTrue(self.clerk._hf_quick_create_blocked("res.partner"))
        self.assertTrue(self.clerk._hf_quick_create_blocked("product.product"))
        self.assertFalse(self.clerk._hf_quick_create_blocked("res.partner.category"))
        self.assertFalse(self.env.ref("base.user_admin")._hf_quick_create_blocked("res.partner"))

    def test_rpc_blocked_for_clerk(self):
        with self.assertRaisesRegex(JsonRpcException, "ValidationError"):
            self._name_create("hf_clerk", "res.partner", "HF Tab Added")
        self.assertFalse(self._partner_exists("HF Tab Added"))

    def test_rpc_allowed_for_admin(self):
        self._name_create("admin", "res.partner", "HF Admin Added")
        self.assertTrue(self._partner_exists("HF Admin Added"))

    def test_rpc_allowed_when_setting_off(self):
        self.env["ir.config_parameter"].set_param(
            "horizonforge_ce_custom.block_quick_create_partner", False)
        self._name_create("hf_clerk", "res.partner", "HF Setting Off")
        self.assertTrue(self._partner_exists("HF Setting Off"))

    def test_server_side_name_create_not_blocked(self):
        # e.g. mail creating a contact from an incoming email
        partner = self.env["res.partner"].with_user(self.clerk).find_or_create(
            "Jane Mailer <jane.mailer@example.com>")
        self.assertEqual(partner.email, "jane.mailer@example.com")

    def test_tab_opens_full_form(self):
        """Typing a new company name and pressing Tab opens the Create form
        instead of saving a bare contact."""
        code = WAIT_FOR + """(async () => {
            const input = await waitFor(".o_field_widget[name='parent_id'] input");
            input.focus();
            input.value = "HF Brand New Co";
            input.dispatchEvent(new Event("input", { bubbles: true }));
            await waitFor(".o-autocomplete--dropdown-menu .o_m2o_dropdown_option_create");
            input.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
            const nameInput = await waitFor(".modal .o_form_view .o_field_widget[name='name'] input");
            if (nameInput.value !== "HF Brand New Co") {
                throw new Error("Create form not prefilled: " + nameInput.value);
            }
            // Leave nothing unsaved behind: discard the dialog, then the form.
            (await waitFor(".modal .o_form_button_cancel")).click();
            for (let i = 0; i < 50 && document.querySelector(".modal"); i++) {
                await new Promise((r) => setTimeout(r, 100));
            }
            (await waitFor(".o_form_button_cancel")).click();
            console.log("test successful");
        })().catch((e) => console.error(e.message));"""
        self.browser_js("/odoo/action-base.action_partner_form/new", code, login="hf_clerk")
        self.assertFalse(self._partner_exists("HF Brand New Co"))
