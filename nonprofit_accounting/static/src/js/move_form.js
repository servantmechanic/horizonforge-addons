/** @odoo-module */
import { registry } from "@web/core/registry";
import { useEffect } from "@odoo/owl";
const { DateTime } = luxon;
import { formView } from "@web/views/form/form_view";
import { FormController } from "@web/views/form/form_controller";

/**
 * Bills, deposits and journal entries: tabbing out of the last header field
 * goes straight to a new line (Account first) instead of stopping on the
 * notebook tabs, when the entry has no lines yet. On a date field, + and -
 * move the date a day later or earlier (from today when empty).
 */
export class NpMoveFormController extends FormController {
    setup() {
        super.setup();
        useEffect(
            (root) => {
                if (!root) {
                    return;
                }
                const onFocusIn = (ev) => {
                    const from = ev.relatedTarget;
                    if (
                        !ev.target.closest(".o_notebook_headers") ||
                        !from ||
                        !from.closest(".o_form_sheet .o_inner_group")
                    ) {
                        return;
                    }
                    const lines = root.querySelector(".o_field_widget[name='item_line_ids']");
                    const add = lines?.querySelector(".o_field_x2many_list_row_add a");
                    if (add && !lines.querySelector(".o_data_row")) {
                        add.click();
                    }
                };
                const onKeydown = (ev) => {
                    const step = { "+": 1, "=": 1, "-": -1 }[ev.key];
                    const widget = ev.target.closest(".o_field_date");
                    if (!step || !widget || ev.ctrlKey || ev.altKey || ev.metaKey) {
                        return;
                    }
                    const name = widget.getAttribute("name");
                    const record = this.model.root;
                    if (!(name in record.data)) {
                        return;
                    }
                    ev.preventDefault();
                    ev.stopPropagation();
                    const current = record.data[name] || DateTime.local().startOf("day");
                    record.update({ [name]: current.plus({ days: step }) });
                };
                root.addEventListener("focusin", onFocusIn);
                root.addEventListener("keydown", onKeydown, true);
                return () => {
                    root.removeEventListener("focusin", onFocusIn);
                    root.removeEventListener("keydown", onKeydown, true);
                };
            },
            () => [this.rootRef.el]
        );
    }
}

registry.category("views").add("np_move_form", {
    ...formView,
    Controller: NpMoveFormController,
});
