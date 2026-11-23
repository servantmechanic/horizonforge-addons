import { Component, onMounted, onPatched, onWillStart, onWillUnmount, useRef, useState } from "@odoo/owl";
import { browser } from "@web/core/browser/browser";
import { _t } from "@web/core/l10n/translation";
import { ConfirmationDialog } from "@web/core/confirmation_dialog/confirmation_dialog";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { useSetupAction } from "@web/search/action_hook";
import { FormViewDialog } from "@web/views/view_dialogs/form_view_dialog";
import { standardActionServiceProps } from "@web/webclient/actions/action_service";
import { GradebookChart } from "./gradebook_chart";
import { GradebookHelpDialog, GradebookPromptDialog } from "./gradebook_dialogs";

const SAVE_DELAY = 500; // ms: cells are sent in batches, at most this often
const GRADE_WIDTH = 84; // px, the sticky grade column
const CATEGORY_WIDTH = 64; // px, each sticky category average column
const COMMENT_WIDTH = 200; // px, the sticky report card comment column
const SHOW_CATEGORIES_KEY = "school_gradebook.show_categories";
const SHOW_COMMENTS_KEY = "school_gradebook.show_comments";
const HIDE_CHART_KEY = "school_gradebook.hide_chart";
const RETRY_DELAY = 4000; // ms: wait before retrying after a failed save
const MAX_UNDO = 200;
const MODE_LABELS = { percent: "%", points: _t("pts"), wrong: _t("wrong"), letter: _t("letter") };

const cellKey = (assignmentId, studentId) => `${assignmentId}:${studentId}`;

/** Numbers as typed: 88, 87.5, not 88.00. */
function formatNumber(value) {
    return String(Math.round(value * 100) / 100);
}

/** Round half up, as the grade engine does: 92.5 becomes 93. */
function roundHalfUp(value, digits) {
    const factor = 10 ** digits;
    return Math.round((value + Number.EPSILON) * factor) / factor;
}

/**
 * The gradebook: students down the side, assignments across the top.
 * Keyboard only, every cell saved as you leave it.
 *
 * A cell is `{ value, status, comment, percent }` with status "scored",
 * "excused" or "missing"; an empty cell has no entry in `state.cells`.
 * `value` is what was typed: a number, or a letter (A-) in a letter column.
 */
export class GradebookGrid extends Component {
    static template = "horizonforge_school_gradebook.GradebookGrid";
    static components = { GradebookChart };
    static props = { ...standardActionServiceProps };

    setup() {
        this.orm = useService("orm");
        this.dialog = useService("dialog");
        this.notification = useService("notification");
        this.action = useService("action");
        this.root = useRef("root");
        this.editor = useRef("editor");
        this.state = useState({
            loaded: false,
            sections: [],
            periods: [],
            sectionId: false,
            periodId: false,
            currentPeriodId: false,
            assignments: [],
            students: [],
            categories: {},
            cells: {},
            grades: {}, // student id -> { grade, letter, categories: { id: average } }
            classAverage: "",
            categoryColumns: [], // weighted categories, for the average columns
            showCategories: browser.localStorage.getItem(SHOW_CATEGORIES_KEY) === "1",
            showComments: browser.localStorage.getItem(SHOW_COMMENTS_KEY) === "1",
            showChart: browser.localStorage.getItem(HIDE_CHART_KEY) !== "1",
            missingAsZero: true,
            cellLetters: false,
            tabAddsColumn: true,
            letterOnly: false,
            gradeDecimals: 0,
            scales: {}, // scale id -> [{ letter, min, value }], highest first
            comments: {}, // student id -> report card comment for the period
            unsaved: {}, // cell key -> "pending" | "failed"
            canEdit: false,
            locked: false,
            hasSchedule: false,
            entryMode: "percent",
            enterDirection: "down",
            nameOrder: "last_first",
            today: "",
            row: 0,
            col: 0,
            editing: false,
            saveStatus: "saved", // saved | saving | offline
        });
        this.pending = new Map(); // cell key -> change waiting to be sent
        this.inflight = new Map(); // cell key -> change being sent
        this.undoStack = [];
        this.redoStack = [];
        this.saveTimer = null;
        this.lastSave = 0;
        // The text being typed is kept out of the reactive state: a
        // keystroke must not re-render the whole grid.
        this.editInitial = "";
        this.editStartedByTyping = false;
        this.needsEditorFocus = false;

        const context = this.props.action.context || {};
        const local = this.props.state || {};
        onWillStart(() =>
            this.load(local.sectionId || context.default_section_id || false, local.periodId || false)
        );
        onMounted(() => {
            this.afterRender(); // bring today's column into view
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
            getLocalState: () => ({ sectionId: this.state.sectionId, periodId: this.state.periodId }),
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

    async load(sectionId, periodId, { keepSelection = false } = {}) {
        const data = await this.orm.call("school.section", "gradebook_open", [], {
            section_id: sectionId,
            period_id: periodId,
        });
        this.applyData(data, keepSelection);
    }

    applyData(data, keepSelection) {
        const state = this.state;
        state.sections = data.sections;
        state.sectionId = data.section_id;
        state.enterDirection = data.enter_direction;
        state.nameOrder = data.name_order || "last_first";
        state.cellLetters = Boolean(data.cell_letters);
        state.tabAddsColumn = data.tab_adds_column !== false;
        state.letterOnly = Boolean(data.letter_only);
        state.gradeDecimals = data.grade_decimals || 0;
        state.missingAsZero = data.missing_as_zero !== false;
        state.scales = data.scales || {};
        state.comments = data.comments || {};
        state.periods = data.periods || [];
        state.periodId = data.period_id || false;
        state.currentPeriodId = data.current_period_id || false;
        state.assignments = data.assignments || [];
        state.students = data.students || [];
        state.categories = Object.fromEntries((data.categories || []).map((c) => [c.id, c]));
        state.canEdit = Boolean(data.can_edit);
        state.locked = Boolean(data.locked);
        state.hasSchedule = Boolean(data.has_schedule);
        state.fillHint = data.fill_hint || "";
        state.statusNote = data.status_note || "";
        state.entryMode = data.entry_mode || "percent";
        state.today = data.today || "";
        state.grades = data.grades || {};
        state.classAverage = data.class_average || "";
        state.categoryColumns = (data.categories || []).filter((c) => (data.weights || {})[c.id]);
        const cells = {};
        for (const score of data.scores || []) {
            cells[cellKey(score.assignment_id, score.student_id)] = {
                value: score.value,
                status: score.status,
                comment: score.comment,
                percent: score.percent,
            };
        }
        // Cells typed but not saved yet win over what the server sent.
        for (const [key, change] of [...this.inflight, ...this.pending]) {
            if (change.status) {
                cells[key] = { ...change.cell };
            } else {
                delete cells[key];
            }
        }
        state.cells = cells;
        if (keepSelection) {
            state.row = Math.min(state.row, Math.max(state.students.length - 1, 0));
            state.col = Math.min(state.col, Math.max(state.assignments.length - 1, 0));
        } else {
            state.row = 0;
            state.col = this.defaultColumn();
            this.undoStack = [];
            this.redoStack = [];
        }
        state.editing = false;
        state.loaded = true;
        this.needsScroll = true;
    }

    /** Today's assignment, else the latest one before today. */
    defaultColumn() {
        const { assignments, today } = this.state;
        let col = 0;
        assignments.forEach((assignment, index) => {
            if (assignment.date <= today) {
                col = index;
            }
        });
        return col;
    }

    /** Pick up what others changed, when the window gets the focus back. */
    async refresh() {
        if (!this.state.loaded || this.state.editing || this.hasUnsaved || !this.state.sectionId) {
            return;
        }
        try {
            const data = await this.orm.silent.call("school.section", "gradebook_open", [], {
                section_id: this.state.sectionId,
                period_id: this.state.periodId,
            });
            if (!this.state.editing && !this.hasUnsaved) {
                this.applyData(data, true);
            }
        } catch {
            // Offline: the grid keeps what it has.
        }
    }

    async reload() {
        await this.flushAll();
        await this.load(this.state.sectionId, this.state.periodId, { keepSelection: true });
        this.focusGrid();
    }

    async onSectionChange(ev) {
        await this.flushAll();
        await this.load(Number(ev.target.value), false);
        this.focusGrid();
    }

    async onPeriodChange(ev) {
        await this.goToPeriod(Number(ev.target.value));
    }

    async goToPeriod(periodId) {
        await this.flushAll();
        await this.load(this.state.sectionId, periodId);
        this.focusGrid();
    }

    /** The current grading period, when the grid shows another one. */
    get otherPeriodWarning() {
        const { periods, periodId, currentPeriodId } = this.state;
        if (!currentPeriodId || periodId === currentPeriodId) {
            return false;
        }
        const shown = periods.find((p) => p.id === periodId);
        const current = periods.find((p) => p.id === currentPeriodId);
        return shown && current ? { shown: shown.name, current } : false;
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

    get activeAssignment() {
        return this.state.assignments[this.state.col];
    }

    get activeStudent() {
        return this.state.students[this.state.row];
    }

    get shownCategories() {
        return this.state.showCategories ? this.state.categoryColumns : [];
    }

    /** Width of the columns that stay in place, for the scroll margins. */
    get rootStyle() {
        const extra =
            GRADE_WIDTH +
            this.shownCategories.length * CATEGORY_WIDTH +
            (this.state.showComments ? COMMENT_WIDTH : 0);
        return `--gb-grade-width: ${GRADE_WIDTH}px; --gb-fixed-extra: ${extra}px;`;
    }

    get commentStyle() {
        const left = GRADE_WIDTH + this.shownCategories.length * CATEGORY_WIDTH;
        return `left: calc(var(--gb-name-width) + ${left}px); min-width: ${COMMENT_WIDTH}px; max-width: ${COMMENT_WIDTH}px;`;
    }

    categoryStyle(index) {
        const left = `calc(var(--gb-name-width) + ${GRADE_WIDTH + index * CATEGORY_WIDTH}px)`;
        return `left: ${left}; min-width: ${CATEGORY_WIDTH}px; max-width: ${CATEGORY_WIDTH}px;`;
    }

    gradeTitle(student) {
        const grade = this.state.grades[student.id];
        if (!grade || !grade.grade) {
            return _t("No scores yet");
        }
        return this.state.categoryColumns
            .filter((category) => grade.categories[category.id] !== undefined)
            .map((category) => `${category.name}: ${grade.categories[category.id]}`)
            .join("  ·  ");
    }

    toggleCategories() {
        this.state.showCategories = !this.state.showCategories;
        browser.localStorage.setItem(SHOW_CATEGORIES_KEY, this.state.showCategories ? "1" : "0");
        this.needsScroll = true;
        this.focusGrid();
    }

    getCell(assignment, student) {
        return this.state.cells[cellKey(assignment.id, student.id)];
    }

    // Letters: each student is graded on their grade level's scale.

    scaleOf(student) {
        return (student && this.state.scales[student.scale_id]) || [];
    }

    /** The percent a typed letter counts for, undefined when not a grade. */
    letterValue(letter, student) {
        const line = this.scaleOf(student).find((l) => l.letter.toUpperCase() === letter.toUpperCase());
        return line ? line.value : undefined;
    }

    letterFor(percent, student) {
        const grade = roundHalfUp(percent, this.state.gradeDecimals);
        const line = this.scaleOf(student).find((l) => grade >= l.min);
        return line ? line.letter : "";
    }

    /** A key that starts one of the student's grades (A, B, ... or S, N, U). */
    startsGrade(key, student) {
        const upper = key.toUpperCase();
        return this.scaleOf(student).some((l) => l.letter.toUpperCase().startsWith(upper));
    }

    /** What a cell shows: letters as typed, percents for everything else. */
    cellText(cell, assignment) {
        if (!cell) {
            return "";
        }
        if (cell.status === "excused") {
            return "EX";
        }
        if (cell.status === "missing") {
            return "M";
        }
        if (assignment.entry_mode === "letter") {
            return cell.value;
        }
        if (assignment.entry_mode === "percent") {
            return formatNumber(cell.value);
        }
        return formatNumber(cell.percent);
    }

    /** The small text beside a score: a letter's percent, or the letter. */
    cellSup(cell, assignment, student) {
        if (!cell || cell.status !== "scored") {
            return "";
        }
        if (assignment.entry_mode === "letter") {
            return formatNumber(cell.percent);
        }
        return this.state.cellLetters ? this.letterFor(cell.percent, student) : "";
    }

    /** The text to edit: what was typed (22 of 25 points, not 88%). */
    editText(cell, assignment) {
        if (!cell || cell.status !== "scored") {
            return this.cellText(cell, assignment);
        }
        return assignment.entry_mode === "letter" ? cell.value : formatNumber(cell.value);
    }

    cellTitle(cell, assignment) {
        if (!cell) {
            return "";
        }
        const parts = [];
        if (cell.status === "scored" && cell.percent !== undefined) {
            if (assignment.entry_mode === "points") {
                parts.push(_t("%(value)s of %(max)s points", {
                    value: formatNumber(cell.value), max: formatNumber(assignment.max_points),
                }));
            } else if (assignment.entry_mode === "wrong") {
                parts.push(_t("%(value)s wrong of %(max)s", {
                    value: formatNumber(cell.value), max: formatNumber(assignment.max_points),
                }));
            } else if (assignment.entry_mode === "letter") {
                parts.push(cell.value);
            }
            parts.push(`${formatNumber(cell.percent)}%`);
        } else if (cell.status === "excused") {
            parts.push(_t("Excused"));
        } else if (cell.status === "missing") {
            parts.push(_t("Missing"));
        }
        if (cell.comment) {
            parts.push(cell.comment);
        }
        return parts.join(" - ");
    }

    cellClass(assignment, student, rowIndex, colIndex) {
        const key = cellKey(assignment.id, student.id);
        const cell = this.state.cells[key];
        const classes = [];
        if (rowIndex === this.state.row && colIndex === this.state.col) {
            classes.push("o_selected");
        }
        if (cell) {
            classes.push(`o_status_${cell.status}`);
            if (cell.comment) {
                classes.push("o_has_comment");
            }
        }
        if (this.state.unsaved[key]) {
            classes.push(`o_unsaved_${this.state.unsaved[key]}`);
        }
        return classes.join(" ");
    }

    // The chart under the grid: counted as the grade engine counts scores.

    chartValue(cell) {
        if (!cell || cell.status === "excused") {
            return null;
        }
        if (cell.status === "missing") {
            return this.state.missingAsZero ? 0 : null;
        }
        return cell.percent;
    }

    get chartAverages() {
        return this.state.assignments.map((assignment) => {
            const values = this.state.students
                .map((student) => this.chartValue(this.getCell(assignment, student)))
                .filter((value) => value !== null && value !== undefined);
            return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null;
        });
    }

    get chartPoints() {
        const student = this.activeStudent;
        return this.state.assignments.map((assignment) =>
            student ? this.chartValue(this.getCell(assignment, student)) ?? null : null
        );
    }

    toggleChart() {
        this.state.showChart = !this.state.showChart;
        browser.localStorage.setItem(HIDE_CHART_KEY, this.state.showChart ? "0" : "1");
        this.focusGrid();
    }

    /** Scores marked missing in the period, for the warning by the name. */
    missingCount(student) {
        return this.state.assignments.filter(
            (assignment) => this.getCell(assignment, student)?.status === "missing"
        ).length;
    }

    headerInfo(assignment) {
        if (assignment.entry_mode === "percent") {
            return "%";
        }
        if (assignment.entry_mode === "letter") {
            return _t("letter");
        }
        return `${formatNumber(assignment.max_points)} ${MODE_LABELS[assignment.entry_mode]}`;
    }

    shortDate(date) {
        const [, month, day] = date.split("-");
        return `${Number(month)}/${Number(day)}`;
    }

    afterRender() {
        if (this.needsEditorFocus && this.editor.el) {
            this.needsEditorFocus = false;
            const input = this.editor.el;
            input.value = this.editInitial;
            input.focus();
            if (this.editStartedByTyping) {
                input.setSelectionRange(input.value.length, input.value.length);
            } else {
                input.select();
            }
        }
        if (this.needsScroll) {
            this.needsScroll = false;
            const selected = this.root.el?.querySelector("td.o_selected");
            if (selected) {
                selected.scrollIntoView({ block: "nearest", inline: "nearest" });
            }
        }
    }

    focusGrid() {
        this.root.el?.querySelector(".o_gradebook_scroll")?.focus({ preventScroll: true });
    }

    // ------------------------------------------------------------------
    // Selection and editing
    // ------------------------------------------------------------------

    select(row, col) {
        const rows = this.state.students.length;
        const cols = this.state.assignments.length;
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

    /** Enter: to the next student, or the next assignment, by preference. */
    moveEnter(backwards) {
        const step = backwards ? -1 : 1;
        if (this.state.enterDirection === "right") {
            if (backwards) {
                this.move(0, -1);
            } else {
                this.moveRight();
            }
        } else {
            this.move(step, 0);
        }
    }

    /**
     * Right, as Tab moves. Past the last column, once it has a score, the
     * next assignment is added (as in Candle), unless the teacher turned
     * that off.
     */
    moveRight() {
        const { col, assignments } = this.state;
        const last = assignments[assignments.length - 1];
        if (
            col === assignments.length - 1 &&
            this.state.canEdit &&
            this.state.tabAddsColumn &&
            last &&
            this.state.students.some((student) => this.getCell(last, student))
        ) {
            this.addAssignment({ after: last });
            return;
        }
        this.move(0, 1);
    }

    get lastAssignment() {
        return this.state.assignments[this.state.assignments.length - 1] || null;
    }

    /**
     * Add the next assignment and go to it, on the same student: Tab past
     * the last column, the + column, or a key in an empty grading period.
     * `category` overrides the category; `typed` starts typing a score.
     */
    async addAssignment({ after = null, category = null, typed = null } = {}) {
        if (this.adding || !this.state.canEdit) {
            return;
        }
        this.adding = true;
        const row = this.state.row;
        try {
            await this.flushAll();
            const id = await this.orm.call("school.section", "gradebook_add_assignment", [
                [this.state.sectionId],
                this.state.periodId,
                after ? after.id : false,
                category ? category.id : false,
            ]);
            await this.load(this.state.sectionId, this.state.periodId, { keepSelection: true });
            const col = this.state.assignments.findIndex((a) => a.id === id);
            this.select(row, col >= 0 ? col : this.state.col);
            this.focusGrid();
            if (typed) {
                this.startEdit(typed);
            }
        } finally {
            this.adding = false;
        }
    }

    /** A category's shortcut key: the column becomes that category. */
    async setCategory(category) {
        const assignment = this.activeAssignment;
        if (!this.state.canEdit || !assignment || assignment.category_id === category.id) {
            return;
        }
        const name = await this.orm.call("school.section", "gradebook_set_category", [
            [this.state.sectionId],
            assignment.id,
            category.id,
        ]);
        assignment.category_id = category.id;
        assignment.name = name;
    }

    /** Categories with a shortcut key, for the legend in the top bar. */
    get shortcutCategories() {
        return Object.values(this.state.categories).filter((c) => c.shortcut);
    }

    startEdit(initial) {
        if (!this.state.canEdit || !this.activeAssignment || !this.activeStudent) {
            return;
        }
        this.editStartedByTyping = initial !== undefined;
        const cell = this.getCell(this.activeAssignment, this.activeStudent);
        this.editInitial = initial !== undefined ? initial : this.editText(cell, this.activeAssignment);
        this.state.editing = true;
        this.needsEditorFocus = true;
    }

    cancelEdit() {
        this.state.editing = false;
        this.focusGrid();
    }

    /**
     * Turn typed text into a cell. Returns `null` for an empty cell,
     * `undefined` (after a warning, unless `quiet`) when the text isn't a
     * valid score.
     */
    parseEntry(text, assignment, current, student, { quiet = false } = {}) {
        const typed = text.trim().toLowerCase();
        const comment = current ? current.comment : "";
        if (typed === "") {
            return null;
        }
        if (assignment.entry_mode === "letter") {
            // A grade of the scale first: a scale could have an M or an X.
            const percent = this.letterValue(typed, student);
            if (percent !== undefined) {
                return { value: typed.toUpperCase(), status: "scored", comment, percent };
            }
        }
        if (typed === "x" || typed === "ex") {
            return { value: false, status: "excused", comment, percent: 0 };
        }
        if (typed === "m") {
            return { value: false, status: "missing", comment, percent: 0 };
        }
        if (assignment.entry_mode === "letter") {
            if (!quiet) {
                const letters = this.scaleOf(student).map((l) => l.letter).join(", ");
                this.notification.add(
                    _t("Enter a grade (%(letters)s), x for excused or m for missing.", { letters }),
                    { type: "warning" }
                );
            }
            return undefined;
        }
        const value = Number(typed.replace(",", ".").replace(/%$/, ""));
        const top = assignment.entry_mode === "percent" ? 100 : assignment.max_points;
        if (!Number.isFinite(value) || value < 0 || value > top) {
            if (!quiet) {
                this.notification.add(
                    _t("Enter a number from 0 to %(top)s, x for excused or m for missing.", {
                        top: formatNumber(top),
                    }),
                    { type: "warning" }
                );
            }
            return undefined;
        }
        return { value, status: "scored", comment, percent: this.toPercent(value, assignment) };
    }

    toPercent(value, assignment) {
        if (assignment.entry_mode === "percent") {
            return value;
        }
        if (assignment.entry_mode === "wrong") {
            return ((assignment.max_points - value) / assignment.max_points) * 100;
        }
        return (value / assignment.max_points) * 100;
    }

    /** Save the cell being edited. False when the text was refused. */
    commitEdit() {
        if (!this.state.editing) {
            return true;
        }
        const assignment = this.activeAssignment;
        const student = this.activeStudent;
        const current = this.getCell(assignment, student);
        const input = this.editor.el;
        const cell = this.parseEntry(input ? input.value : this.editInitial, assignment, current, student);
        if (cell === undefined) {
            input?.focus();
            return false;
        }
        this.state.editing = false;
        this.changeCells([{ assignment, student, cell }]);
        this.focusGrid();
        return true;
    }

    // ------------------------------------------------------------------
    // Changing cells, undo and redo
    // ------------------------------------------------------------------

    /** Apply changes `[{assignment, student, cell}]` as one undo step. */
    changeCells(changes, { record = true } = {}) {
        const step = [];
        for (const { assignment, student, cell } of changes) {
            const key = cellKey(assignment.id, student.id);
            const before = this.state.cells[key] || null;
            if (this.sameCell(before, cell)) {
                continue;
            }
            step.push({ assignment, student, before, after: cell });
            this.setCell(assignment, student, cell);
        }
        if (step.length && record) {
            this.undoStack.push(step);
            if (this.undoStack.length > MAX_UNDO) {
                this.undoStack.shift();
            }
            this.redoStack = [];
        }
        return step.length;
    }

    sameCell(a, b) {
        if (!a || !b) {
            return !a && !b;
        }
        return a.status === b.status && a.value === b.value && (a.comment || "") === (b.comment || "");
    }

    setCell(assignment, student, cell) {
        const key = cellKey(assignment.id, student.id);
        if (cell) {
            this.state.cells[key] = { ...cell };
        } else {
            delete this.state.cells[key];
        }
        this.pending.set(key, {
            assignment_id: assignment.id,
            student_id: student.id,
            status: cell ? cell.status : false,
            value: cell && cell.status === "scored" ? cell.value : false,
            comment: cell ? cell.comment || "" : "",
            cell,
        });
        this.state.unsaved[key] = "pending";
        // The first change goes out at once, so the grade column follows
        // as you type; the next ones are batched.
        this.scheduleSave(Math.max(0, SAVE_DELAY - (Date.now() - this.lastSave)));
    }

    undo() {
        const step = this.undoStack.pop();
        if (!step) {
            return;
        }
        for (const change of step) {
            this.setCell(change.assignment, change.student, change.before);
        }
        this.redoStack.push(step);
        this.selectChange(step[0]);
    }

    redo() {
        const step = this.redoStack.pop();
        if (!step) {
            return;
        }
        for (const change of step) {
            this.setCell(change.assignment, change.student, change.after);
        }
        this.undoStack.push(step);
        this.selectChange(step[0]);
    }

    selectChange(change) {
        const row = this.state.students.findIndex((s) => s.id === change.student.id);
        const col = this.state.assignments.findIndex((a) => a.id === change.assignment.id);
        if (row >= 0 && col >= 0) {
            this.select(row, col);
        }
    }

    setStatus(status) {
        const assignment = this.activeAssignment;
        const student = this.activeStudent;
        if (!this.state.canEdit || !assignment || !student) {
            return;
        }
        const current = this.getCell(assignment, student);
        const cell = status
            ? { value: false, status, comment: current ? current.comment : "", percent: 0 }
            : null;
        this.changeCells([{ assignment, student, cell }]);
    }

    editComment() {
        const assignment = this.activeAssignment;
        const student = this.activeStudent;
        if (!this.state.canEdit || !assignment || !student) {
            return;
        }
        const current = this.getCell(assignment, student);
        if (!current) {
            this.notification.add(_t("Enter a score first, then add the note."), { type: "info" });
            return;
        }
        this.dialog.add(
            GradebookPromptDialog,
            {
                title: _t("Note: %(student)s, %(assignment)s", {
                    student: student.name,
                    assignment: assignment.name,
                }),
                value: current.comment || "",
                onConfirm: (comment) => {
                    const latest = this.getCell(assignment, student);
                    if (latest) {
                        this.changeCells([{ assignment, student, cell: { ...latest, comment } }]);
                    }
                },
            },
            { onClose: () => this.focusGrid() }
        );
    }

    fillColumn() {
        const assignment = this.activeAssignment;
        if (!this.state.canEdit || !assignment) {
            return;
        }
        this.dialog.add(
            GradebookPromptDialog,
            {
                title: _t("Fill empty cells: %(assignment)s", { assignment: assignment.name }),
                label: _t("Score for every student without one"),
                confirmLabel: _t("Fill"),
                onConfirm: (text) => {
                    const empty = this.state.students.filter((student) => !this.getCell(assignment, student));
                    // Checked on the first student, with a warning; a letter
                    // counts by each student's own scale.
                    if (!empty.length || !this.parseEntry(text, assignment, null, empty[0])) {
                        return;
                    }
                    const changes = [];
                    for (const student of empty) {
                        const cell = this.parseEntry(text, assignment, null, student, { quiet: true });
                        if (cell) {
                            changes.push({ assignment, student, cell });
                        }
                    }
                    this.changeCells(changes);
                },
            },
            { onClose: () => this.focusGrid() }
        );
    }

    /** Paste a column or block copied from a spreadsheet, from the selected cell. */
    onPaste(ev) {
        if (this.state.editing || !this.state.canEdit) {
            return;
        }
        const text = ev.clipboardData?.getData("text/plain");
        if (!text) {
            return;
        }
        ev.preventDefault();
        const lines = text.replace(/\r/g, "").replace(/\n$/, "").split("\n");
        const changes = [];
        let skipped = 0;
        lines.forEach((line, dRow) => {
            line.split("\t").forEach((text, dCol) => {
                const student = this.state.students[this.state.row + dRow];
                const assignment = this.state.assignments[this.state.col + dCol];
                if (!student || !assignment) {
                    skipped++;
                    return;
                }
                if (text.trim() === "") {
                    return; // an empty pasted cell leaves the score alone
                }
                const current = this.getCell(assignment, student);
                const cell = this.parseEntry(text, assignment, current, student, { quiet: true });
                if (!cell) {
                    skipped++;
                    return;
                }
                changes.push({ assignment, student, cell });
            });
        });
        const count = this.changeCells(changes);
        if (skipped) {
            this.notification.add(
                _t("%(count)s cells pasted, %(skipped)s skipped (not a valid score, or outside the grid).", {
                    count,
                    skipped,
                }),
                { type: "warning" }
            );
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

    /** Send the waiting cells. One request at a time. */
    async flush() {
        if (this.inflight.size || !this.pending.size) {
            return;
        }
        this.inflight = this.pending;
        this.pending = new Map();
        this.lastSave = Date.now();
        const changes = [...this.inflight.values()].map(({ cell, ...change }) => change);
        let result;
        try {
            result = await this.orm.silent.call("school.score", "save_batch", [changes]);
        } catch {
            // The server can't be reached: keep the cells and try again.
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
            const key = cellKey(saved.assignment_id, saved.student_id);
            if (this.pending.has(key)) {
                continue; // changed again while saving
            }
            delete this.state.unsaved[key];
            if (saved.status && this.state.cells[key]) {
                this.state.cells[key].percent = saved.percent;
            }
        }
        for (const grades of result.grades || []) {
            if (grades.section_id === this.state.sectionId && grades.period_id === this.state.periodId) {
                this.state.grades = grades.grades;
                this.state.classAverage = grades.class_average;
            }
        }
        for (const error of result.errors) {
            const key = cellKey(error.assignment_id, error.student_id);
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

    /** Save everything now, before leaving or reloading. */
    async flushAll() {
        if (this.state.editing) {
            this.commitEdit();
        }
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
    // Assignments
    // ------------------------------------------------------------------

    openAssignment(assignmentId) {
        if (!this.state.sectionId) {
            return;
        }
        this.dialog.add(
            FormViewDialog,
            {
                resModel: "school.assignment",
                resId: assignmentId || false,
                title: assignmentId ? _t("Assignment") : _t("New assignment"),
                context: {
                    default_section_id: this.state.sectionId,
                    school_gradebook_dialog: true,
                },
                preventEdit: !this.state.canEdit,
                canExpand: false,
                removeRecord:
                    assignmentId && this.state.canEdit
                        ? () => this.confirmDelete(assignmentId)
                        : undefined,
                size: "md",
                onRecordSaved: (record) => {
                    this.newAssignmentId = assignmentId ? false : record.resId;
                },
            },
            {
                onClose: async () => {
                    await this.reload();
                    if (this.newAssignmentId) {
                        const col = this.state.assignments.findIndex((a) => a.id === this.newAssignmentId);
                        this.newAssignmentId = false;
                        if (col >= 0) {
                            this.select(0, col);
                        }
                    }
                },
            }
        );
    }

    /** Resolves once deleted. Stays pending on Cancel, so the form stays open. */
    confirmDelete(assignmentId) {
        return new Promise((resolve) => {
            this.dialog.add(ConfirmationDialog, {
                title: _t("Delete assignment"),
                body: _t("Delete this assignment and all its scores? This can't be undone."),
                confirmLabel: _t("Delete"),
                confirm: async () => {
                    await this.orm.unlink("school.assignment", [assignmentId]);
                    resolve();
                },
                cancel: () => {},
            });
        });
    }

    async generateAssignments() {
        await this.flushAll();
        const result = await this.orm.call("school.section", "gradebook_generate", [
            [this.state.sectionId],
            this.state.periodId,
        ]);
        this.notification.add(result.message, { type: result.count ? "success" : "info" });
        await this.reload();
    }

    toggleComments() {
        this.state.showComments = !this.state.showComments;
        browser.localStorage.setItem(SHOW_COMMENTS_KEY, this.state.showComments ? "1" : "0");
        this.needsScroll = true;
        this.focusGrid();
    }

    async toggleCellLetters() {
        this.state.cellLetters = !this.state.cellLetters;
        this.focusGrid();
        await this.orm.call("school.section", "gradebook_set_cell_letters", [this.state.cellLetters]);
    }

    /** The student's report card comment for this class and period. */
    editReportComment(student) {
        if (!student) {
            return;
        }
        if (!this.state.canEdit) {
            if (this.state.comments[student.id]) {
                this.notification.add(this.state.comments[student.id], { title: student.name });
            }
            return;
        }
        const period = this.state.periods.find((p) => p.id === this.state.periodId);
        this.dialog.add(
            GradebookPromptDialog,
            {
                title: _t("Report card comment: %(student)s, %(period)s", {
                    student: student.name,
                    period: period ? period.name : "",
                }),
                value: this.state.comments[student.id] || "",
                multiline: true,
                onConfirm: async (comment) => {
                    const saved = await this.orm.call("school.section", "gradebook_set_comment", [
                        [this.state.sectionId],
                        this.state.periodId,
                        student.id,
                        comment,
                    ]);
                    if (saved) {
                        this.state.comments[student.id] = saved;
                    } else {
                        delete this.state.comments[student.id];
                    }
                },
            },
            { onClose: () => this.focusGrid() }
        );
    }

    async toggleEnterDirection() {
        const direction = this.state.enterDirection === "down" ? "right" : "down";
        this.state.enterDirection = direction;
        this.focusGrid();
        await this.orm.call("school.section", "gradebook_set_enter_direction", [direction]);
    }

    /** Students by last name or by first name: kept per user. */
    async toggleNameOrder() {
        const order = this.state.nameOrder === "last_first" ? "first_last" : "last_first";
        const student = this.activeStudent;
        await this.flushAll();
        await this.orm.call("school.student", "grid_set_name_order", [order]);
        await this.load(this.state.sectionId, this.state.periodId, { keepSelection: true });
        // Stay on the same student in the new order.
        const row = student ? this.state.students.findIndex((s) => s.id === student.id) : -1;
        if (row >= 0) {
            this.select(row, this.state.col);
        }
        this.focusGrid();
    }

    showHelp() {
        this.dialog.add(GradebookHelpDialog, {}, { onClose: () => this.focusGrid() });
    }

    // ------------------------------------------------------------------
    // Mouse and keyboard
    // ------------------------------------------------------------------

    onCellClick(ev) {
        const td = ev.target.closest("td[data-row]");
        if (!td || ev.target.closest("input")) {
            return;
        }
        if (this.state.editing && !this.commitEdit()) {
            return;
        }
        this.select(Number(td.dataset.row), Number(td.dataset.col));
        this.focusGrid();
    }

    /** Double-click: the comment of a cell with a score, else edit the cell. */
    onCellDblClick(ev) {
        const td = ev.target.closest("td[data-row]");
        if (!td || this.state.editing) {
            return;
        }
        this.select(Number(td.dataset.row), Number(td.dataset.col));
        if (this.state.canEdit && this.getCell(this.activeAssignment, this.activeStudent)) {
            this.editComment();
        } else {
            this.startEdit();
        }
    }

    onEditorBlur(ev) {
        // Leaving the cell with the mouse saves it, like leaving it with a
        // key. A refused value is dropped rather than trapping the focus.
        if (!this.state.editing || this.needsEditorFocus || !document.hasFocus()) {
            return;
        }
        const assignment = this.activeAssignment;
        const student = this.activeStudent;
        const current = this.getCell(assignment, student);
        const cell = this.parseEntry(ev.target.value, assignment, current, student, { quiet: true });
        this.state.editing = false;
        if (cell !== undefined) {
            this.changeCells([{ assignment, student, cell }]);
        }
    }

    onKeydown(ev) {
        if (!this.state.loaded || ev.target.closest(".o_gradebook_bar")) {
            return;
        }
        const handled = this.state.editing ? this.onEditKey(ev) : this.onNavigationKey(ev);
        if (handled) {
            ev.preventDefault();
            ev.stopPropagation();
        }
    }

    onEditKey(ev) {
        const key = ev.key;
        if (key === "Escape") {
            this.cancelEdit();
            return true;
        }
        if (key === "Enter") {
            if (this.commitEdit()) {
                this.moveEnter(ev.shiftKey);
            }
            return true;
        }
        if (key === "Tab") {
            if (this.commitEdit()) {
                if (ev.shiftKey) {
                    this.move(0, -1);
                } else {
                    this.moveRight();
                }
            }
            return true;
        }
        if (key === "ArrowUp" || key === "ArrowDown") {
            if (this.commitEdit()) {
                this.move(key === "ArrowUp" ? -1 : 1, 0);
            }
            return true;
        }
        // Left and right move between cells after typing a number, and
        // inside the text after F2 (as in a spreadsheet).
        if ((key === "ArrowLeft" || key === "ArrowRight") && this.editStartedByTyping) {
            if (this.commitEdit()) {
                this.move(0, key === "ArrowLeft" ? -1 : 1);
            }
            return true;
        }
        return false;
    }

    onNavigationKey(ev) {
        const key = ev.key;
        const ctrl = ev.ctrlKey || ev.metaKey;
        if (ctrl && ev.shiftKey) {
            if (key.toLowerCase() === "a") {
                if (this.state.canEdit) {
                    this.openAssignment(false);
                }
                return true;
            }
            if (key.toLowerCase() === "f") {
                this.fillColumn();
                return true;
            }
        }
        if (ctrl && !ev.shiftKey) {
            if (key.toLowerCase() === "z") {
                this.undo();
                return true;
            }
            if (key.toLowerCase() === "y") {
                this.redo();
                return true;
            }
            return false; // Ctrl+V arrives as a paste event; leave the rest to the browser
        }
        if (ev.altKey) {
            return false;
        }
        const category = key.length === 1 && this.shortcutCategories.find((c) => c.shortcut === key);
        // An empty grading period: a key starts it with a first assignment.
        if (!this.state.assignments.length) {
            if (!this.state.canEdit || !this.state.students.length) {
                return false;
            }
            if (category) {
                this.addAssignment({ category });
                return true;
            }
            if (key === "Tab" || key === "Enter") {
                this.addAssignment();
                return true;
            }
            if (/^[0-9]$/.test(key)) {
                this.addAssignment({ typed: key });
                return true;
            }
        }
        if (category) {
            this.setCategory(category);
            return true;
        }
        // In a letter column a letter key starts a grade, before any
        // shortcut (as absence codes do in the attendance grid): on the
        // E/S/N/U scale N is a grade there, and a double-click the note.
        if (
            this.activeAssignment?.entry_mode === "letter" &&
            this.state.canEdit &&
            /^[a-z]$/i.test(key) &&
            this.startsGrade(key, this.activeStudent)
        ) {
            this.startEdit(key.toUpperCase());
            return true;
        }
        switch (key) {
            case "ArrowUp":
                this.move(-1, 0);
                return true;
            case "ArrowDown":
                this.move(1, 0);
                return true;
            case "ArrowLeft":
                this.move(0, -1);
                return true;
            case "ArrowRight":
                this.move(0, 1);
                return true;
            case "Enter":
                this.moveEnter(ev.shiftKey);
                return true;
            case "Tab":
                if (ev.shiftKey) {
                    this.move(0, -1);
                } else {
                    this.moveRight();
                }
                return true;
            case "Home":
                this.select(this.state.row, 0);
                return true;
            case "End":
                this.select(this.state.row, this.state.assignments.length - 1);
                return true;
            case "PageUp":
                this.move(-10, 0);
                return true;
            case "PageDown":
                this.move(10, 0);
                return true;
            case "F2":
                this.startEdit();
                return true;
            case "Delete":
            case "Backspace":
                this.setStatus(false);
                return true;
            case "x":
            case "X":
                this.setStatus("excused");
                return true;
            case "m":
            case "M":
                this.setStatus("missing");
                return true;
            case "n":
            case "N":
                this.editComment(); // a note, as in the attendance grid
                return true;
            case "r":
            case "R":
                this.editReportComment(this.activeStudent);
                return true;
            case "?":
                this.showHelp();
                return true;
        }
        if (/^[0-9.,]$/.test(key)) {
            this.startEdit(key);
            return true;
        }
        return false;
    }
}

registry.category("actions").add("school_gradebook_grid", GradebookGrid);
