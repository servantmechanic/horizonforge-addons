from odoo.tests import TransactionCase, new_test_user, tagged

PARAM = "horizonforge_ce_custom.simple_interface"


@tagged("post_install", "-at_install")
class TestSimpleInterface(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.clerk = new_test_user(cls.env, login="hf_clerk", groups="base.group_user")
        cls.admin = new_test_user(cls.env, login="hf_admin", groups="base.group_system")
        cls.discuss = cls.env.ref("mail.menu_root_discuss")
        cls.apps = cls.env.ref("base.menu_management")

    def _set(self, on):
        self.env["res.config.settings"].create({"hf_simple_interface": on}).execute()

    def _menu_ids(self, user):
        menus = self.env["ir.ui.menu"].with_user(user).load_menus(False)
        return set(menus["root"]["children"])

    def test_off_by_default(self):
        self.assertFalse(self.clerk._hf_simple_interface())

    def test_hides_menus_from_non_admins(self):
        self._set(True)
        self.assertTrue(self.clerk._hf_simple_interface())
        clerk_menus = self._menu_ids(self.clerk)
        self.assertNotIn(self.discuss.id, clerk_menus)
        self.assertNotIn(self.apps.id, clerk_menus)
        self.assertNotIn(self.discuss, self.env["ir.ui.menu"].with_user(self.clerk).get_user_roots())
        # Administrators keep everything.
        self.assertFalse(self.admin._hf_simple_interface())
        self.assertIn(self.discuss.id, self._menu_ids(self.admin))

    def test_turning_off_shows_menus_again(self):
        self._set(True)
        self.assertNotIn(self.discuss.id, self._menu_ids(self.clerk))
        self._set(False)
        self.assertIn(self.discuss.id, self._menu_ids(self.clerk))

    def test_no_odoobot_onboarding(self):
        if "odoobot_state" not in self.env["res.users"]._fields:
            self.skipTest("mail_bot is not installed")
        self._set(True)
        self.clerk.odoobot_state = "not_initialized"
        self.clerk.with_user(self.clerk)._on_webclient_bootstrap()
        self.assertEqual(self.clerk.odoobot_state, "disabled")
        # Not for administrators.
        self.admin.odoobot_state = "not_initialized"
        self.admin.with_user(self.admin)._on_webclient_bootstrap()
        self.assertNotEqual(self.admin.odoobot_state, "disabled")
