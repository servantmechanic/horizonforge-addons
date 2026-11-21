import { serializeDate } from "@web/core/l10n/dates";
import { registry } from "@web/core/registry";
import { calendarView } from "@web/views/calendar/calendar_view";
import { CalendarController } from "@web/views/calendar/calendar_controller";

// The School Calendar with a Print button: prints the school year of the
// month on screen (or the current year) as a year-at-a-glance PDF.
export class SchoolCalendarController extends CalendarController {
    async onPrintCalendar() {
        const action = await this.orm.call("school.year", "action_print_calendar_for_date", [
            serializeDate(this.model.date),
        ]);
        await this.action.doAction(action);
    }
}

registry.category("views").add("school_calendar", {
    ...calendarView,
    Controller: SchoolCalendarController,
    buttonTemplate: "horizonforge_school_core.SchoolCalendarButtons",
});
