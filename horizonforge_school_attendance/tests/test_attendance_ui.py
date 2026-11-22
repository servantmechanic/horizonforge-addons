from datetime import timedelta

from odoo import Command, fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.horizonforge_school_core.tests.common import SchoolCoreCase

HELPERS = """
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const waitFor = async (check, what) => {
    for (let i = 0; i < 100; i++) {
        const found = typeof check === "string" ? document.querySelector(check) : check();
        if (found) { return found; }
        await sleep(100);
    }
    throw new Error("Timed out: " + (what || check));
};
const press = async (key, options = {}) => {
    document.activeElement.dispatchEvent(
        new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options }));
    await sleep(30);
};
const cell = (row, date) => {
    const col = [...document.querySelectorAll("th.o_attendance_day")].findIndex((th) => th.dataset.date === date);
    return document.querySelector(`td[data-row="${row}"][data-col="${col}"]`);
};
const expect = (actual, wanted, what) => {
    if (actual !== wanted) { throw new Error(`${what}: expected "${wanted}", got "${actual}"`); }
};
const saved = () => waitFor(
    () => document.querySelector(".o_attendance_status").dataset.status === "saved"
        && !document.querySelector("td.o_unsaved_pending, td.o_unsaved_failed"),
    "cells saved");
const focused = () => waitFor(
    () => document.activeElement.classList.contains("o_attendance_scroll"), "grid focused");
"""


@tagged("post_install", "-at_install")
class TestAttendanceUi(HttpCase, SchoolCoreCase):
    """The attendance grid in a real browser."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        today = fields.Date.context_today(cls.env.user)
        # A school year around today, and a school day to work on: the
        # Wednesday of this week.
        cls.year.period_ids.unlink()
        cls.year.write({
            "date_start": today - timedelta(days=60), "date_end": today + timedelta(days=60),
        })
        cls.env["school.period"].create({
            "year_id": cls.year.id, "name": "Now",
            "date_start": cls.year.date_start, "date_end": cls.year.date_end,
        })
        cls.env["school.calendar.day"].search([]).unlink()
        monday = today - timedelta(days=today.weekday())
        cls.wednesday = monday + timedelta(days=2)
        cls.thursday = monday + timedelta(days=3)
        cls.ui_teacher = new_test_user(
            cls.env, login="att_teacher", password="att_teacher",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        cls.env["school.homeroom"].search([]).action_archive()
        cls.homeroom = cls.env["school.homeroom"].create({
            "name": "Test Lower Room",
            "teacher_id": cls.ui_teacher.id,
            "grade_level_ids": [Command.set(cls.level_5.ids)],
        })
        cls.section_5.teacher_id = cls.ui_teacher
        cls.section_5.action_enroll_grade_levels()

    def test_take_attendance(self):
        wednesday = fields.Date.to_string(self.wednesday)
        thursday = fields.Date.to_string(self.thursday)
        code = HELPERS + f"""(async () => {{
            await waitFor("td.o_selected");
            await focused();
            expect(document.querySelectorAll(".o_attendance_student").length, 2, "students");
            // Click Anna's Wednesday, mark absent with the A key.
            cell(0, "{wednesday}").click();
            await focused();
            await press("a");
            expect(cell(0, "{wednesday}").textContent.trim(), "A", "absent");
            await press("ArrowDown");
            await press("t");
            expect(cell(1, "{wednesday}").textContent.trim(), "T", "tardy");
            await saved();
            const total = (row, n) => document.querySelectorAll("tbody tr")[row].querySelectorAll("td.o_attendance_total")[n].textContent.trim();
            await waitFor(() => total(0, 0) === "1", "absent total");
            expect(total(1, 1), "1", "tardy total");

            // Part day on Thursday, then cleared: present again. Undo brings it back.
            await press("ArrowUp");
            await press("ArrowRight");
            await press("h");
            expect(cell(0, "{thursday}").textContent.trim(), "H", "half day");
            await press("Delete");
            expect(cell(0, "{thursday}").textContent.trim(), "", "cleared");
            await press("z", {{ ctrlKey: true }});
            expect(cell(0, "{thursday}").textContent.trim(), "H", "undo");
            await saved();
            await waitFor(() => total(0, 0) === "1.5", "total with half day");

            // A note on the absence.
            await press("ArrowLeft");
            await press("n");
            const input = await waitFor(".o_attendance_note_input");
            input.value = "Sick";
            input.dispatchEvent(new Event("input", {{ bubbles: true }}));
            input.dispatchEvent(new KeyboardEvent("keydown", {{ key: "Enter", bubbles: true }}));
            await waitFor(() => cell(0, "{wednesday}").classList.contains("o_has_note"), "note mark");
            await saved();

            // Double-click Ben's tardy for a note.
            cell(1, "{wednesday}").dispatchEvent(new MouseEvent("dblclick", {{ bubbles: true }}));
            const input2 = await waitFor(".o_attendance_note_input");
            input2.value = "Late bus";
            input2.dispatchEvent(new Event("input", {{ bubbles: true }}));
            input2.dispatchEvent(new KeyboardEvent("keydown", {{ key: "Enter", bubbles: true }}));
            await waitFor(() => cell(1, "{wednesday}").classList.contains("o_has_note"), "note by double-click");
            await saved();

            // Next week and back, then the whole grading period.
            document.querySelector(".o_attendance_next").click();
            await waitFor(() => !cell(0, "{wednesday}"), "next week");
            document.querySelector(".o_attendance_today").click();
            await waitFor(() => cell(0, "{wednesday}"), "this week");
            expect(cell(0, "{wednesday}").textContent.trim(), "A", "kept after reload");
            document.querySelector(".o_attendance_period").click();
            await waitFor(() => document.querySelectorAll("th.o_attendance_day").length > 20, "period view");
            console.log('test successful');
        }})().catch((e) => console.error(e.message));"""
        self.browser_js(
            "/odoo/action-horizonforge_school_attendance.school_attendance_grid_action",
            code, login="att_teacher", timeout=120,
        )
        records = self.env["school.attendance"].search([("homeroom_id", "=", self.homeroom.id)])
        self.assertEqual(
            sorted(records.mapped(lambda r: (r.student_id.first_name, r.date, r.code_id.code, r.note or ""))),
            [("Anna", self.wednesday, "A", "Sick"), ("Anna", self.thursday, "H", ""),
             ("Ben", self.wednesday, "T", "Late bus")],
        )
