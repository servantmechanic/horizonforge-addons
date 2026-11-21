import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { Dialog } from "@web/core/dialog/dialog";
import { _t } from "@web/core/l10n/translation";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";

const SAVE_DELAY = 500; // ms: cells are sent in batches, at most this often
const RETRY_DELAY = 4000;
const MAX_UNDO = 200;

const cellKey = (studentId, date) => `${studentId}:${date}`;

class AttendanceNoteDialog extends Component {
    static template = "horizonforge_school_attendance.NoteDialog";
    static components = { Dialog };
    static props = { close: Function, title: String, value: String, onConfirm: Function };

    setup() {
        this.state = useState({ value: this.props.value });
        this.input = useRef("input");
        onMounted(() => {
            this.input.el.focus();
            this.input.el.select();
        });
    }

    onKeydown(ev) {
        ev.stopPropagation();
        if (ev.key === "Enter") {
            ev.preventDefault();
            this.confirm();
        }
    }

    confirm() {
        this.props.onConfirm(this.state.value.trim());
        this.props.close();
    }
}

/**
 * Daily attendance of one homeroom: students down the side, weekdays
 * across the top. Everyone is present unless a code is recorded, so the
 * teacher only types the exceptions: the code's letter on a student's day.
 *
 * A cell is `{ code_id, note }`; a present student has no cell.
 */
export class AttendanceGrid extends Component {
    static template = "horizonforge_school_attendance.AttendanceGrid";
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.root = useRef("root");
        this.state = useState({
            loaded: false,
            homerooms: [],
            homeroomId: false,
            date: false,
            mode: "week",
            nameOrder: "last_first",
            days: [],
            students: [],
            codes: [],
            cells: {},
            totals: {},
            unsaved: {},
            canEdit: false,
            locked: false,
            periodName: "",
            rangeLabel: "",
            today: "",
            row: 0,
            col: 0,
            saveStatus: "saved",
        });
        this.pending = new Map();
        this.inflight = new Map();
        this.undoStack = [];
        this.redoStack = [];
        this.saveTimer = null;
        this.lastSave = 0;
        this.totalRange = {};

        const local = this.props.state || {};
        onWillStart(() => this.load(local.homeroomId || false, local.date || false, local.mode || "week"));
        onMounted(() => {
            this.afterRender();
            this.focusGrid();
            this.onWindowFocus = () => this.refresh();
            window.addEventListener("focus", this.onWindowFocus);
        });
        onWillUnmount(() => {
            window.removeEventListener("focus", this.onWindowFocus);
            clearTimeout(this.saveTimer);
        });
        onPatched(() => this.afterRender());
        useSetupAction({
            rootRef: this.root,
            getLocalState: () => ({
                homeroomId: this.state.homeroomId,
                date: this.state.date,
                mode: this.state.mode,
            }),
            beforeLeave: () => this.flushAll(),
            beforeUnload: (ev) => {
                if (this.hasUnsaved) {
                    this.flush();
                    ev.preventDefault();
                    ev.returnValue = "";
                }
            },
        });
    }

    // ------------------------------------------------------------------
    // Loading
    // ------------------------------------------------------------------

    async load(homeroomId, date, mode, { keepSelection = false } = {}) {
        const data = await this.orm.call("school.attendance", "attendance_open", [], {
            homeroom_id: homeroomId,
            date,
            mode,
        });
        this.applyData(data, keepSelection);
    }

    applyData(data, keepSelection) {
        const state = this.state;
        state.homerooms = data.homerooms;
        state.homeroomId = data.homeroom_id;
        state.date = data.date;
        state.mode = data.mode;
        state.nameOrder = data.name_order || "last_first";
        state.today = data.today;
        state.days = data.days;
        state.students = data.students;
        state.codes = data.codes;
        state.totals = data.totals;
        state.canEdit = Boolean(data.can_edit);
        state.locked = Boolean(data.locked);
        state.periodName = data.period_name;
        state.rangeLabel = data.range_label;
        this.totalRange = { total_from: data.total_from || false, total_to: data.total_to || false };
        const cells = {};
        for (const record of data.records) {
            cells[cellKey(record.student_id, record.date)] = { code_id: record.code_id, note: record.note };
        }
        for (const [key, change] of [...this.inflight, ...this.pending]) {
            if (change.code_id) {
                cells[key] = { code_id: change.code_id, note: change.note };
            } else {
                delete cells[key];
            }
        }
        state.cells = cells;
        if (keepSelection) {
            state.row = Math.min(state.row, Math.max(state.students.length - 1, 0));
            state.col = Math.min(state.col, Math.max(state.days.length - 1, 0));
        } else {
            state.row = 0;
            state.col = this.defaultColumn();
            this.undoStack = [];
            this.redoStack = [];
        }
        state.loaded = true;
        this.needsScroll = true;
    }

    /** Today's column, else the first school day shown. */
    defaultColumn() {
        const { days, today } = this.state;
        const todayIndex = days.findIndex((day) => day.date === today && !day.off);
        if (todayIndex >= 0) {
            return todayIndex;
        }
        const first = days.findIndex((day) => !day.off);
        return Math.max(first, 0);
    }

    async refresh() {
        if (!this.state.loaded || this.hasUnsaved || !this.state.homeroomId) {
            return;
        }
        try {
            const data = await this.orm.silent.call("school.attendance", "attendance_open", [], {
                homeroom_id: this.state.homeroomId,
                date: this.state.date,
                mode: this.state.mode,
            });
            if (!this.hasUnsaved) {
                this.applyData(data, true);
            }
        } catch {
            // Offline: keep what is shown.
        }
    }

    async go(homeroomId, date, mode) {
        await this.flushAll();
        await this.load(homeroomId, date, mode);
        this.focusGrid();
    }

    onHomeroomChange(ev) {
        return this.go(Number(ev.target.value), this.state.date, this.state.mode);
    }

    /** Previous or next week (or grading period). */
    shift(direction) {
        const days = this.state.days;
        const edge = new Date((direction < 0 ? days[0] : days[days.length - 1]).date + "T12:00:00");
        // Past the edge of what is shown: the weekend, then the next range.
        edge.setDate(edge.getDate() + direction * 3);
        const date = edge.toISOString().slice(0, 10);
        return this.go(this.state.homeroomId, date, this.state.mode);
    }

    goToday() {
        return this.go(this.state.homeroomId, false, this.state.mode);
    }

    setMode(mode) {
        return this.go(this.state.homeroomId, this.state.date, mode);
    }

    /** Students by last name or by first name: kept per user. */
    async toggleNameOrder() {
        const order = this.state.nameOrder === "last_first" ? "first_last" : "last_first";
        const student = this.state.students[this.state.row];
        await this.flushAll();
        await this.orm.call("school.student", "grid_set_name_order", [order]);
        await this.load(this.state.homeroomId, this.state.date, this.state.mode, { keepSelection: true });
        const row = student ? this.state.students.findIndex((s) => s.id === student.id) : -1;
        if (row >= 0) {
            this.select(row, this.state.col);
        }
        this.focusGrid();
    }

    // ------------------------------------------------------------------
    // Rendering helpers
    // ------------------------------------------------------------------

    get hasUnsaved() {
        return this.pending.size > 0 || this.inflight.size > 0;
    }

    get saveStatusLabel() {
        return {
            saved: _t("Saved"),
            saving: _t("Saving..."),
            offline: _t("Offline, retrying"),
        }[this.state.saveStatus];
    }

    get codesById() {
        return Object.fromEntries(this.state.codes.map((code) => [code.id, code]));
    }

    getCell(student, day) {
        return this.state.cells[cellKey(student.id, day.date)];
    }

    cellClass(student, day, rowIndex, colIndex) {
        const key = cellKey(student.id, day.date);
        const classes = [];
        if (day.off) {
            classes.push("o_day_off");
        }
        if (rowIndex === this.state.row && colIndex === this.state.col) {
            classes.push("o_selected");
        }
        if (this.state.cells[key]?.note) {
            classes.push("o_has_note");
        }
        if (this.state.unsaved[key]) {
            classes.push(`o_unsaved_${this.state.unsaved[key]}`);
        }
        return classes.join(" ");
    }

    cellTitle(cell, day) {
        if (day.off) {
            return day.off_name;
        }
        if (!cell) {
            return _t("Present");
        }
        const code = this.codesById[cell.code_id];
        return [code ? code.name : "", cell.note].filter(Boolean).join(" - ");
    }

    afterRender() {
        if (this.needsScroll) {
            this.needsScroll = false;
            this.root.el?.querySelector("td.o_selected")?.scrollIntoView({ block: "nearest", inline: "nearest" });
        }
    }

    focusGrid() {
        this.root.el?.querySelector(".o_attendance_scroll")?.focus({ preventScroll: true });
    }

    // ------------------------------------------------------------------
    // Changing cells
    // ------------------------------------------------------------------

    select(row, col) {
        const rows = this.state.students.length;
        const cols = this.state.days.length;
        if (!rows || !cols) {
            return;
        }
        this.state.row = Math.max(0, Math.min(rows - 1, row));
        this.state.col = Math.max(0, Math.min(cols - 1, col));
        this.needsScroll = true;
    }

    move(dRow, dCol) {
        this.select(this.state.row + dRow, this.state.col + dCol);
    }

    get active() {
        const student = this.state.students[this.state.row];
        const day = this.state.days[this.state.col];
        return student && day && !day.off && this.state.canEdit ? { student, day } : null;
    }

    changeCell(student, day, cell, { record = true } = {}) {
        const key = cellKey(student.id, day.date);
        const before = this.state.cells[key] || null;
        if ((before?.code_id || false) === (cell?.code_id || false) && (before?.note || "") === (cell?.note || "")) {
            return;
        }
        if (record) {
            this.undoStack.push({ student, day, before, after: cell });
            if (this.undoStack.length > MAX_UNDO) {
                this.undoStack.shift();
            }
            this.redoStack = [];
        }
        if (cell) {
            this.state.cells[key] = { ...cell };
        } else {
            delete this.state.cells[key];
        }
        this.pending.set(key, {
            student_id: student.id,
            date: day.date,
            code_id: cell ? cell.code_id : false,
            note: cell ? cell.note || "" : "",
        });
        this.state.unsaved[key] = "pending";
        this.scheduleSave(Math.max(0, SAVE_DELAY - (Date.now() - this.lastSave)));
    }

    setCode(code) {
        const active = this.active;
        if (!active) {
            return;
        }
        const current = this.getCell(active.student, active.day);
        this.changeCell(active.student, active.day, { code_id: code.id, note: current ? current.note : "" });
    }

    clearCell() {
        const active = this.active;
        if (active) {
            this.changeCell(active.student, active.day, null);
        }
    }

    editNote() {
        const active = this.active;
        if (!active) {
            return;
        }
        const current = this.getCell(active.student, active.day);
        if (!current) {
            this.notification.add(_t("Record the absence or tardy first, then add the note."), { type: "info" });
            return;
        }
        this.dialog.add(
            AttendanceNoteDialog,
            {
                title: _t("Note: %(student)s, %(day)s", { student: active.student.name, day: active.day.label }),
                value: current.note || "",
                onConfirm: (note) => {
                    const latest = this.getCell(active.student, active.day);
                    if (latest) {
                        this.changeCell(active.student, active.day, { ...latest, note });
                    }
                },
            },
            { onClose: () => this.focusGrid() }
        );
    }

    undo() {
        const step = this.undoStack.pop();
        if (step) {
            this.changeCell(step.student, step.day, step.before, { record: false });
            this.redoStack.push(step);
        }
    }

    redo() {
        const step = this.redoStack.pop();
        if (step) {
            this.changeCell(step.student, step.day, step.after, { record: false });
            this.undoStack.push(step);
        }
    }

    // ------------------------------------------------------------------
    // Saving
    // ------------------------------------------------------------------

    scheduleSave(delay) {
        if (this.saveTimer === null) {
            this.saveTimer = setTimeout(() => {
                this.saveTimer = null;
                this.flush();
            }, delay);
        }
        if (this.state.saveStatus === "saved") {
            this.state.saveStatus = "saving";
        }
    }

    async flush() {
        if (this.inflight.size || !this.pending.size) {
            return;
        }
        this.inflight = this.pending;
        this.pending = new Map();
        this.lastSave = Date.now();
        let result;
        try {
            result = await this.orm.silent.call(
                "school.attendance", "save_batch", [[...this.inflight.values()]], this.totalRange
            );
        } catch {
            for (const [key, change] of this.inflight) {
                if (!this.pending.has(key)) {
                    this.pending.set(key, change);
                }
                this.state.unsaved[key] = "failed";
            }
            this.inflight = new Map();
            this.state.saveStatus = "offline";
            this.scheduleSave(RETRY_DELAY);
            return;
        }
        const sent = this.inflight;
        this.inflight = new Map();
        for (const saved of result.saved) {
            const key = cellKey(saved.student_id, saved.date);
            if (!this.pending.has(key)) {
                delete this.state.unsaved[key];
            }
        }
        Object.assign(this.state.totals, result.totals || {});
        for (const error of result.errors) {
            const key = cellKey(error.student_id, error.date);
            if (!this.pending.has(key) && sent.has(key)) {
                this.state.unsaved[key] = "failed";
            }
            this.notification.add(error.message, { type: "danger", sticky: true });
        }
        if (this.pending.size) {
            this.scheduleSave(SAVE_DELAY);
            this.state.saveStatus = "saving";
        } else {
            this.state.saveStatus = "saved";
        }
    }

    async flushAll() {
        clearTimeout(this.saveTimer);
        this.saveTimer = null;
        for (let tries = 0; tries < 3 && this.hasUnsaved; tries++) {
            if (this.inflight.size) {
                await new Promise((resolve) => setTimeout(resolve, 100));
                tries--;
                continue;
            }
            await this.flush();
            clearTimeout(this.saveTimer);
            this.saveTimer = null;
            if (this.state.saveStatus === "offline") {
                break;
            }
        }
        if (this.pending.size) {
            this.scheduleSave(RETRY_DELAY);
        }
    }

    // ------------------------------------------------------------------
    // Mouse and keyboard
    // ------------------------------------------------------------------

    onCellClick(ev) {
        const td = ev.target.closest("td[data-row]");
        if (td) {
            this.select(Number(td.dataset.row), Number(td.dataset.col));
            this.focusGrid();
        }
    }

    onCellDblClick(ev) {
        const td = ev.target.closest("td[data-row]");
        if (td) {
            this.select(Number(td.dataset.row), Number(td.dataset.col));
            this.editNote();
        }
    }

    onLegendClick(code) {
        this.setCode(code);
        this.focusGrid();
    }

    onKeydown(ev) {
        if (!this.state.loaded || ev.target.closest(".o_attendance_bar")) {
            return;
        }
        if (this.handleKey(ev)) {
            ev.preventDefault();
            ev.stopPropagation();
        }
    }

    handleKey(ev) {
        const key = ev.key;
        if (ev.ctrlKey || ev.metaKey) {
            if (key.toLowerCase() === "z" && !ev.shiftKey) {
                this.undo();
                return true;
            }
            if (key.toLowerCase() === "y") {
                this.redo();
                return true;
            }
            return false;
        }
        if (ev.altKey) {
            return false;
        }
        switch (key) {
            case "ArrowUp":
                this.move(-1, 0);
                return true;
            case "ArrowDown":
            case "Enter":
                this.move(ev.shiftKey ? -1 : 1, 0);
                return true;
            case "ArrowLeft":
                this.move(0, -1);
                return true;
            case "ArrowRight":
                this.move(0, 1);
                return true;
            case "Tab":
                this.move(0, ev.shiftKey ? -1 : 1);
                return true;
            case "Delete":
            case "Backspace":
            case " ":
                this.clearCell();
                return true;
        }
        if (key.length === 1) {
            const code = this.state.codes.find((c) => c.code === key.toUpperCase());
            if (code) {
                this.setCode(code);
                return true;
            }
            if (key.toLowerCase() === "n") {
                this.editNote();
                return true;
            }
        }
        return false;
    }
}

registry.category("actions").add("school_attendance_grid", AttendanceGrid);
