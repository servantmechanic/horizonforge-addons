import { registry } from "@web/core/registry";
import { calendarView } from "@web/views/calendar/calendar_view";
import { CalendarController } from "@web/views/calendar/calendar_controller";
import { CalendarRenderer } from "@web/views/calendar/calendar_renderer";
import { CalendarCommonRenderer } from "@web/views/calendar/calendar_common/calendar_common_renderer";

// Lessons are whole days: the week and day views list them per day, without
// the hour grid.
const DAY_GRID = { day: "dayGridDay", week: "dayGridWeek" };

export class PlannerCalendarCommonRenderer extends CalendarCommonRenderer {
    get options() {
        const options = super.options;
        const view = DAY_GRID[this.props.model.scale];
        if (view) {
            options.initialView = view;
            options.dayMaxEventRows = false; // every lesson of the day shows
        }
        // Each day's classes in the teacher's order (their guides' order),
        // then the guide's order.
        const records = this.props.model.records;
        const key = (event) => {
            const record = records[event.id]?.rawRecord || {};
            return [record.class_order || 0, record.section_id?.id || 0, Number(event.id)];
        };
        options.eventOrder = (a, b) => {
            const [ka, kb] = [key(a), key(b)];
            for (let i = 0; i < ka.length; i++) {
                if (ka[i] !== kb[i]) {
                    return ka[i] - kb[i];
                }
            }
            return 0;
        };
        return options;
    }
}

export class PlannerCalendarRenderer extends CalendarRenderer {
    static components = {
        ...CalendarRenderer.components,
        day: PlannerCalendarCommonRenderer,
        week: PlannerCalendarCommonRenderer,
        month: PlannerCalendarCommonRenderer,
    };
}

export class PlannerCalendarController extends CalendarController {
    async onWeeklyPlan() {
        await this.action.doAction("horizonforge_school_planner.school_weekly_plan_action");
    }
}

registry.category("views").add("school_planner_calendar", {
    ...calendarView,
    Controller: PlannerCalendarController,
    Renderer: PlannerCalendarRenderer,
    buttonTemplate: "horizonforge_school_planner.PlannerCalendarButtons",
});
