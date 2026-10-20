import { registry } from "@web/core/registry";

// Hide the odoo.com links (Help, My Odoo.com Account) from the user menu.
const userMenuItems = registry.category("user_menuitems");
userMenuItems.remove("support");
userMenuItems.remove("odoo_account");
