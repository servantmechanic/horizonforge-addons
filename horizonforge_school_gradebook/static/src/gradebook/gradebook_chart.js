import { Component, onMounted, onWillUnmount, useRef, useState } from "@odoo/owl";

// Same chart as the printed Class Performance report (models/school_chart.py).
const HEIGHT = 170;
const PAD = { left: 30, right: 12, top: 10, bottom: 20 };

/** Bottom of the percent axis: 60, or lower in steps of 10 to fit. */
function valueFloor(values) {
    const present = values.filter((v) => v !== null && v !== undefined);
    const low = present.length ? Math.min(...present) : 100;
    return Math.max(0, Math.min(60, Math.floor(low / 10) * 10));
}

/** Runs of consecutive points, split where a value is missing. */
function segments(values) {
    const runs = [];
    let run = [];
    values.forEach((value, index) => {
        if (value === null || value === undefined) {
            if (run.length) {
                runs.push(run);
            }
            run = [];
        } else {
            run.push([index, value]);
        }
    });
    if (run.length) {
        runs.push(run);
    }
    return runs;
}

const fmt = (value) => (value === null || value === undefined ? "-" : String(Math.round(value * 10) / 10));

/**
 * The selected student's score on each assignment of the period (blue)
 * beside the class average (gray), under the gradebook grid. Hover for
 * the values.
 */
export class GradebookChart extends Component {
    static template = "horizonforge_school_gradebook.GradebookChart";
    static props = {
        assignments: Array, // [{ id, name, date }]
        averages: Array, // class average per assignment, null without scores
        points: Array, // the student's percent per assignment, null without one
        studentName: String,
    };

    setup() {
        this.root = useRef("root");
        this.state = useState({ width: 600, hover: null });
        onMounted(() => {
            this.observer = new ResizeObserver(([entry]) => {
                this.state.width = Math.max(240, Math.floor(entry.contentRect.width));
            });
            this.observer.observe(this.root.el);
        });
        onWillUnmount(() => this.observer?.disconnect());
    }

    get height() {
        return HEIGHT;
    }

    get geometry() {
        const count = this.props.assignments.length;
        const plotW = this.state.width - PAD.left - PAD.right;
        const plotH = HEIGHT - PAD.top - PAD.bottom;
        const low = valueFloor([...this.props.averages, ...this.props.points]);
        const step = count > 1 ? plotW / (count - 1) : 0;
        const x = (i) => PAD.left + (count > 1 ? i * step : plotW / 2);
        const y = (v) => PAD.top + ((100 - Math.max(low, Math.min(100, v))) / (100 - low)) * plotH;
        return { count, plotW, plotH, low, step, x, y, base: PAD.top + plotH };
    }

    get gridlines() {
        const { low, y } = this.geometry;
        const every = 100 - low <= 50 ? 10 : 20;
        const lines = [];
        for (let value = low; value <= 100; value += every) {
            lines.push({ value, y: y(value) });
        }
        return lines;
    }

    get xLabels() {
        const { count, x } = this.geometry;
        const every = Math.max(1, Math.ceil(count / Math.max(4, Math.floor(this.state.width / 36))));
        const labels = [];
        for (let i = 0; i < count; i++) {
            // The last number too, unless it would touch the one before.
            const last = i === count - 1 && (count - 1) % every > Math.floor(every / 2);
            if (i % every === 0 || last) {
                labels.push({ label: i + 1, x: x(i) });
            }
        }
        return labels;
    }

    pointsAttr(run) {
        const { x, y } = this.geometry;
        return run.map(([i, v]) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
    }

    get averageAreas() {
        const { x, y, base } = this.geometry;
        return segments(this.props.averages).map((run) => ({
            area: `${x(run[0][0]).toFixed(1)},${base} ${this.pointsAttr(run)} ${x(run[run.length - 1][0]).toFixed(1)},${base}`,
            line: run.length > 1 ? this.pointsAttr(run) : "",
            // A lone point has no line: a dot shows it.
            dot: run.length === 1 ? { cx: x(run[0][0]), cy: y(run[0][1]) } : null,
        }));
    }

    get studentLines() {
        return segments(this.props.points)
            .filter((run) => run.length > 1)
            .map((run) => this.pointsAttr(run));
    }

    get studentDots() {
        const { x, y, count, step } = this.geometry;
        const roomy = count <= 1 || step >= 12;
        return segments(this.props.points)
            .filter((run) => roomy || run.length === 1)
            .flat()
            .map(([i, v]) => ({ key: i, cx: x(i), cy: y(v) }));
    }

    get hover() {
        const index = this.state.hover;
        if (index === null || index >= this.props.assignments.length) {
            return null;
        }
        const { x, y } = this.geometry;
        const assignment = this.props.assignments[index];
        const average = this.props.averages[index];
        const point = this.props.points[index];
        const left = x(index);
        return {
            x: left,
            number: index + 1,
            name: assignment.name,
            average: fmt(average),
            point: fmt(point),
            avgY: average === null || average === undefined ? null : y(average),
            pointY: point === null || point === undefined ? null : y(point),
            // Keep the tooltip inside the chart.
            style: left > this.state.width / 2 ? `right: ${this.state.width - left + 10}px;` : `left: ${left + 10}px;`,
        };
    }

    onMove(ev) {
        const { count, step } = this.geometry;
        if (!count) {
            return;
        }
        const rect = ev.currentTarget.getBoundingClientRect();
        const offset = ev.clientX - rect.left - PAD.left;
        const index = count > 1 ? Math.round(offset / step) : 0;
        this.state.hover = Math.max(0, Math.min(count - 1, index));
    }

    onLeave() {
        this.state.hover = null;
    }
}
