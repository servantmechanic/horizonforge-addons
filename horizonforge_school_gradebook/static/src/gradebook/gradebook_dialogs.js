import { Component, onMounted, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";

/** One text value: a cell comment, or the value to fill a column with. */
export class GradebookPromptDialog extends Component {
    static template = "horizonforge_school_gradebook.PromptDialog";
    static components = { Dialog };
    static props = {
        close: Function,
        title: String,
        label: { type: String, optional: true },
        value: { type: String, optional: true },
        confirmLabel: { type: String, optional: true },
        multiline: { type: Boolean, optional: true },
        onConfirm: Function,
    };

    setup() {
        this.state = useState({ value: this.props.value || "" });
        this.input = useRef("input");
        onMounted(() => {
            this.input.el.focus();
            this.input.el.select();
        });
    }

    onKeydown(ev) {
        // Keep the keys inside the dialog: the grid behind must not react.
        ev.stopPropagation();
        if (ev.key === "Enter" && !(this.props.multiline && ev.shiftKey)) {
            ev.preventDefault();
            this.confirm();
        }
    }

    confirm() {
        this.props.onConfirm(this.state.value.trim());
        this.props.close();
    }
}

export class GradebookHelpDialog extends Component {
    static template = "horizonforge_school_gradebook.HelpDialog";
    static components = { Dialog };
    static props = { close: Function };
}
