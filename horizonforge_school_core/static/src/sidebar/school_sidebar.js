import { Component, useEffect, useState } from "@odoo/owl";
import { router } from "@web/core/browser/router";
import { useBus, useService } from "@web/core/utils/hooks";
import { session } from "@web/session";
import { WebClient } from "@web/webclient/webclient";

const SCHOOL_APP = "horizonforge_school_core.menu_school_root";

// Icons for the School menus; other menus get a plain dot.
const ICONS = {
    "horizonforge_school_gradebook.menu_school_gradebook_root": "fa-th",
    "horizonforge_school_attendance.menu_school_attendance_root": "fa-calendar-check-o",
    "horizonforge_school_core.menu_school_classes": "fa-graduation-cap",
    "horizonforge_school_core.menu_school_students": "fa-user",
    "horizonforge_school_core.menu_school_patrons": "fa-address-book-o",
    "horizonforge_school_core.menu_school_enrollments": "fa-list-alt",
    "horizonforge_school_core.menu_school_calendar": "fa-calendar",
    "horizonforge_school_documents.menu_school_documents_root": "fa-folder-open-o",
    "horizonforge_school_gradebook.menu_school_grade_reports": "fa-bar-chart",
    "horizonforge_school_core.menu_school_config": "fa-cog",
};

/** The menus under `menu` that open something, depth first. */
function leaves(menu) {
    if (!menu.childrenTree.length) {
        return menu.actionID ? [menu] : [];
    }
    return menu.childrenTree.flatMap(leaves);
}

/**
 * Left-hand menu for the School app on wide screens: every School menu is
 * one click away. A menu with sub-menus opens its first one (Gradebook opens
 * the grid) and lists the others under it while one of them is open. The
 * top-bar menus are hidden while it shows; small screens keep Odoo's own
 * menu.
 */
export class SchoolSidebar extends Component {
    static template = "horizonforge_school_core.SchoolSidebar";
    static props = {};

    setup() {
        this.menuService = useService("menu");
        this.actionService = useService("action");
        this.ui = useState(useService("ui"));
        this.state = useState({ activeId: false, menusVersion: 0 });
        this.version = session.school_version;
        useBus(this.env.bus, "MENUS:APP-CHANGED", () => this.state.menusVersion++);
        useBus(this.env.bus, "ACTION_MANAGER:UI-UPDATED", () => this.syncActive());
        useEffect(
            (visible) => {
                document.body.classList.toggle("o_school_sidebar_on", visible);
                return () => document.body.classList.remove("o_school_sidebar_on");
            },
            () => [this.visible]
        );
    }

    get app() {
        const app = this.menuService.getCurrentApp();
        return app && app.xmlid === SCHOOL_APP ? app : null;
    }

    get visible() {
        return Boolean(this.app) && !this.ui.isSmall;
    }

    get sections() {
        // Read so that the list is rebuilt when the menus reload.
        this.state.menusVersion;
        return this.menuService.getMenuAsTree(this.app.id).childrenTree;
    }

    leaves(section) {
        return leaves(section);
    }

    /** Highlight the menu that opened the first breadcrumb. */
    syncActive() {
        if (!this.app) {
            return;
        }
        // The controller's state is set before this event; the router's
        // current state may still be the previous one.
        const stack = this.actionService.currentController?.state?.actionStack
            || router.current.actionStack;
        const root = stack?.[0]?.action ?? this.actionService.currentAction?.id;
        if (root === undefined) {
            return;
        }
        const found = this.sections
            .flatMap(leaves)
            .find((m) => m.actionID === Number(root) || (m.actionPath && m.actionPath === root));
        if (found) {
            this.state.activeId = found.id;
        }
    }

    contains(section) {
        return leaves(section).some((m) => m.id === this.state.activeId);
    }

    isOpen(section) {
        return section.childrenTree.length > 0 && this.contains(section);
    }

    icon(section) {
        return ICONS[section.xmlid] || "fa-circle-o";
    }

    href(menu) {
        const target = leaves(menu)[0];
        return target ? `/odoo/${target.actionPath || "action-" + target.actionID}` : "#";
    }

    onClick(ev, menu) {
        // Ctrl-, Shift- or middle-click follow the link in a new tab.
        if (ev.ctrlKey || ev.metaKey || ev.shiftKey || ev.button !== 0) {
            return;
        }
        ev.preventDefault();
        const target = leaves(menu)[0];
        if (target) {
            this.state.activeId = target.id;
            this.menuService.selectMenu(target);
        }
    }
}

WebClient.components = { ...WebClient.components, SchoolSidebar };
