import { useEffect, useRef } from "@odoo/owl";
import { patch } from "@web/core/utils/patch";
import { DateTimeField } from "@web/views/fields/datetime/datetime_field";

const { DateTime } = luxon;
const STEPS = { "+": 1, "=": 1, "-": -1 };

/**
 * On any editable date (or date and time) field, + and - move the date a
 * day later or earlier, from today when empty; = works as + without Shift.
 * Only while the box shows the field's own date (or nothing), so typing a
 * date in a format that uses dashes still works.
 */
patch(DateTimeField.prototype, {
    setup() {
        super.setup();
        const root = useRef("root");
        useEffect(
            (el) => {
                if (!el) {
                    return;
                }
                const onKeydown = (ev) => this.onHfDateKey(ev);
                el.addEventListener("keydown", onKeydown);
                return () => el.removeEventListener("keydown", onKeydown);
            },
            () => [root.el]
        );
    },

    onHfDateKey(ev) {
        const step = STEPS[ev.key];
        const target = ev.target;
        const fieldName = target.dataset?.field;
        if (!step || !fieldName || ev.defaultPrevented || ev.ctrlKey || ev.altKey || ev.metaKey) {
            return;
        }
        if (this.props.readonly || !(fieldName in this.props.record.data)) {
            return;
        }
        const index = fieldName === this.startDateField ? 0 : 1;
        if (target.tagName === "INPUT" && target.value && target.value !== this.getFormattedValue(index, true)) {
            return; // the user is typing a date
        }
        ev.preventDefault();
        ev.stopPropagation();
        const current = this.props.record.data[fieldName];
        const start = current || (this.field.type === "date" ? DateTime.local().startOf("day") : DateTime.local());
        this.props.record.update({ [fieldName]: start.plus({ days: step }) });
    },
});
