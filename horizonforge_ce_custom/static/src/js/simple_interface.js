import { registry } from "@web/core/registry";
import { session } from "@web/session";
// Imported so that their systray items are registered before we remove them.
import "@mail/core/public_web/messaging_menu";
import "@mail/core/web/activity_menu";

// Simple interface (Settings > General Settings > Interface): users who are
// not administrators get no chat (Discuss / OdooBot) or activity icons.
if (session.hf_simple_interface) {
    const systray = registry.category("systray");
    systray.remove("mail.messaging_menu");
    systray.remove("mail.activity_menu");
}
