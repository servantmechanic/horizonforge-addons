from odoo import release
from odoo.tests import HttpCase, new_test_user, tagged

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
class TestSchoolSidebar(HttpCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.teacher = new_test_user(
            cls.env, login="sidebar_teacher", password="sidebar_teacher",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )

    def test_version(self):
        module = self.env["ir.module.module"].search([("name", "=", "horizonforge_school_core")])
        version = self.env["ir.module.module"]._school_version()
        self.assertTrue(version)
        self.assertEqual(release.series + "." + version, module.latest_version)

    def test_sidebar_one_click(self):
        """The School menus are in a sidebar, one click each, and the top-bar
        menus are hidden."""
        version = self.env["ir.module.module"]._school_version()
        code = WAIT_FOR + """(async () => {
            const sidebar = await waitFor(".o_school_sidebar");
            const sections = document.querySelector(".o_main_navbar .o_menu_sections");
            if (sections && sections.offsetParent !== null) {
                throw new Error("top-bar menus still shown");
            }
            if (!sidebar.querySelector(".o_school_sidebar_version").textContent.includes("%s")) {
                throw new Error("no version in the sidebar");
            }
            const xmlid = "horizonforge_school_core.menu_school_classes";
            sidebar.querySelector(`[data-menu-xmlid="${xmlid}"]`).click();
            await waitFor(".o_list_view", "classes list");
            await waitFor(`.o_school_sidebar_item.active[data-menu-xmlid="${xmlid}"]`, "Classes highlighted");
            console.log("test successful");
        })().catch((e) => console.error(e.message));""" % version
        self.browser_js(
            "/odoo/action-horizonforge_school_core.school_student_action",
            code, login="sidebar_teacher",
        )
