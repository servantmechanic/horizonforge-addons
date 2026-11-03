import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { Dropdown } from "@web/core/dropdown/dropdown";
import { useDropdownState } from "@web/core/dropdown/dropdown_hooks";
import { deserializeDateTime } from "@web/core/l10n/dates";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

const { DateTime } = luxon;

/**
 * Header icon for the running timesheet timer of the OCA module
 * hr_timesheet_time_control: shows the elapsed time and lets the user stop it,
 * open its task or start work, like the attendance check-in icon.
 */
export class TimerSystray extends Component {
    static components = { Dropdown };
    static props = [];
    static template = "horizonforge_project_custom.TimerSystray";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.dropdown = useDropdownState();
        this.state = useState({ enabled: false, timer: false, now: DateTime.now() });
        // Timers start and stop from task and timesheet buttons too: refresh
        // after each screen change, and tick the elapsed time every 30 seconds.
        this.onUiUpdated = () => this.load();
        onWillStart(() => this.load());
        onMounted(() => {
            this.env.bus.addEventListener("ACTION_MANAGER:UI-UPDATED", this.onUiUpdated);
            this.interval = setInterval(() => (this.state.now = DateTime.now()), 30000);
        });
        onWillUnmount(() => {
            this.env.bus.removeEventListener("ACTION_MANAGER:UI-UPDATED", this.onUiUpdated);
            clearInterval(this.interval);
        });
    }

    async load() {
        const result = await this.orm.call("account.analytic.line", "hf_get_running_timer", []);
        this.state.enabled = result.enabled;
        this.state.timer = result.running ? result : false;
        this.state.now = DateTime.now();
    }

    get start() {
        return deserializeDateTime(this.state.timer.start);
    }

    get elapsed() {
        const minutes = Math.max(0, Math.floor(this.state.now.diff(this.start, "minutes").minutes));
        return `${Math.floor(minutes / 60)}:${String(minutes % 60).padStart(2, "0")}`;
    }

    get startLabel() {
        return this.start.toLocaleString(DateTime.TIME_SIMPLE);
    }

    async afterChange() {
        await this.load();
        // Refresh the screen behind, so its Start and Stop buttons match.
        await this.action.doAction("soft_reload");
    }

    async stop() {
        this.dropdown.close();
        const elapsed = this.elapsed;
        await this.orm.call("account.analytic.line", "button_end_work", [[this.state.timer.id]]);
        this.notification.add(_t("Timer stopped: %s logged.", elapsed), { type: "success" });
        await this.afterChange();
    }

    async startWork() {
        this.dropdown.close();
        await this.action.doAction(
            {
                name: _t("Start work"),
                type: "ir.actions.act_window",
                res_model: "hr.timesheet.switch",
                views: [[false, "form"]],
                target: "new",
            },
            { onClose: () => this.afterChange() }
        );
    }

    async openTask() {
        this.dropdown.close();
        await this.action.doAction({
            type: "ir.actions.act_window",
            res_model: "project.task",
            res_id: this.state.timer.task_id,
            views: [[false, "form"]],
        });
    }
}

registry
    .category("systray")
    .add("horizonforge_project_custom.timer_systray", { Component: TimerSystray }, { sequence: 102 });
