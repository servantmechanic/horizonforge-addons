from unittest.mock import patch

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestTweaks(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.acme = cls.env["res.partner"].create({
            "name": "HF Acme Supply",
            "is_company": True,
            "email": "office@hf-acme.example.com",
            "phone": "555-0100",
        })

    def _warning(self, vals):
        return self.env["res.partner"].new(vals)._onchange_hf_duplicate_warning()

    def test_duplicate_warning_by_name(self):
        result = self._warning({"name": "hf acme supply"})
        self.assertIn("HF Acme Supply", result["warning"]["message"])

    def test_duplicate_warning_by_email_and_phone(self):
        self.assertTrue(self._warning({"name": "X", "email": "OFFICE@hf-acme.example.com"}))
        self.assertTrue(self._warning({"name": "X", "phone": "555-0100"}))

    def test_no_warning_for_new_name(self):
        self.assertIsNone(self._warning({"name": "HF Nobody Like Me"}))

    def test_no_warning_for_wildcards(self):
        self.assertIsNone(self._warning({"name": "HF Acme%"}))

    def test_no_warning_for_own_company_contact(self):
        # A contact under Acme sharing Acme's phone is not a duplicate.
        self.assertIsNone(self._warning({
            "name": "HF Acme Buyer", "parent_id": self.acme.id, "phone": "555-0100",
        }))

    def test_no_warning_against_itself(self):
        partner = self.acme.with_context(active_test=False)
        self.assertIsNone(partner._onchange_hf_duplicate_warning())

    def test_publisher_warranty_does_not_call_home(self):
        with patch("odoo.addons.mail.models.update.requests.post") as post:
            self.assertTrue(self.env["publisher_warranty.contract"].update_notification())
        post.assert_not_called()

    def test_home_action_on_preferences(self):
        arch = self.env["res.users"].get_views(
            [(self.env.ref("base.view_users_form_simple_modif").id, "form")]
        )["views"]["form"]["arch"]
        self.assertIn('name="action_id"', arch)

    def test_quick_create_settings_default_on(self):
        settings = self.env["res.config.settings"].create({})
        self.assertTrue(settings.hf_block_quick_create_partner)
        self.assertTrue(settings.hf_block_quick_create_product)
