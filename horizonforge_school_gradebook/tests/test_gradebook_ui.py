from odoo import fields
from odoo.tests import HttpCase, new_test_user, tagged

from odoo.addons.horizonforge_school_core.tests.common import SchoolCoreCase

# Helpers for the browser: wait for something, press keys on the grid.
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
    const target = document.activeElement;
    target.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true, ...options }));
    await sleep(30);
};
const type = async (text) => {
    for (const char of text) {
        const editor = document.querySelector(".o_gradebook_editor");
        if (editor) {
            editor.value += char;
        } else {
            await press(char);
            await waitFor(".o_gradebook_editor");
        }
    }
};
const cell = (row, col) => document.querySelector(`td[data-row="${row}"][data-col="${col}"]`);
const selected = () => {
    const td = document.querySelector("td.o_selected");
    return td.dataset.row + "," + td.dataset.col;
};
const expect = (actual, wanted, what) => {
    if (actual !== wanted) { throw new Error(`${what}: expected "${wanted}", got "${actual}"`); }
};
const saved = () => waitFor(
    () => document.querySelector(".o_gradebook_status").dataset.status === "saved"
        && !document.querySelector("td.o_unsaved_pending, td.o_unsaved_failed"),
    "cells saved");
"""


@tagged("post_install", "-at_install")
class TestGradebookUi(HttpCase, SchoolCoreCase):
    """The grid in a real browser: keyboard entry, saving, undo, paste."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # A year around today, so the grid opens on these assignments.
        today = fields.Date.context_today(cls.env.user)
        cls.year.period_ids.unlink()
        cls.year.write({"date_start": today.replace(month=1, day=1), "date_end": today.replace(month=12, day=31)})
        cls.period = cls.env["school.period"].create({
            "year_id": cls.year.id, "name": "All Year",
            "date_start": cls.year.date_start, "date_end": cls.year.date_end,
        })
        cls.section_5.enrollment_ids.unlink()
        cls.section_5.action_enroll_grade_levels()
        homework = cls.env.ref("horizonforge_school_gradebook.score_category_homework")
        cls.lesson, cls.quiz = cls.env["school.assignment"].create([
            {"section_id": cls.section_5.id, "name": "Lesson 1", "date": today,
             "category_id": homework.id, "sequence": 1},
            {"section_id": cls.section_5.id, "name": "Quiz", "date": today,
             "category_id": homework.id, "entry_mode": "points", "max_points": 20, "sequence": 2},
        ])
        cls.ui_teacher = new_test_user(
            cls.env, login="grid_teacher", password="grid_teacher",
            groups="base.group_user,horizonforge_school_core.group_school_teacher",
        )
        cls.section_5.teacher_id = cls.ui_teacher

    def _run(self, steps, login="grid_teacher"):
        code = HELPERS + "(async () => {" + steps + "console.log('test successful'); })()" \
            ".catch((e) => console.error(e.message));"
        self.browser_js(
            "/odoo/action-horizonforge_school_gradebook.school_gradebook_action",
            code, login=login, timeout=120,
        )

    def _scores(self, assignment):
        return {
            score.student_id.first_name: (score.status, score.value_entered, score.comment)
            for score in assignment.score_ids
        }

    def test_keyboard_entry(self):
        self._run("""
            await waitFor("td.o_selected");
            await waitFor(() => document.activeElement.classList.contains("o_gradebook_scroll"), "grid focused");
            // Opens on today's assignments: the last one is selected.
            expect(selected(), "0,1", "start cell");
            await press("ArrowLeft");
            expect(selected(), "0,0", "after left");

            // Type a score, Enter saves and moves down to the next student.
            await type("88");
            await press("Enter");
            expect(selected(), "1,0", "after Enter");
            expect(cell(0, 0).textContent.trim(), "88", "first score");
            await type("92.5");
            await press("Enter");
            expect(cell(1, 0).textContent.trim(), "92.5", "second score");
            await saved();
            // The grade column follows: 88 rounds to a B, the class averages 90.5.
            const gradeOf = (row) => {
                const td = document.querySelectorAll("td.o_gradebook_grade")[row];
                return td.querySelector(".o_gradebook_grade_value").textContent + " " + td.querySelector(".o_gradebook_letter").textContent;
            };
            await waitFor(() => gradeOf(0) === "88 B", "first grade, got " + gradeOf(0));
            expect(gradeOf(1), "93 A", "second grade");
            expect(document.querySelector(".o_gradebook_class_average").textContent.trim(), "90.5", "class average");

            // Out of range: refused, the editor stays open; Esc cancels.
            await press("ArrowUp");
            await type("150");
            await press("Enter");
            await waitFor(".o_notification");
            if (!document.querySelector(".o_gradebook_editor")) { throw new Error("editor closed on a bad value"); }
            await press("Escape");
            expect(cell(0, 0).textContent.trim(), "88", "kept after Esc");

            // Tab moves right: points column, 15 of 20 is 75%.
            await press("Tab");
            expect(selected(), "0,1", "after Tab");
            await type("15");
            await press("Tab");
            await saved();
            expect(cell(0, 1).textContent.trim(), "75", "points shown as a percent");
            expect(cell(0, 1).title, "15 of 20 points - 75%", "points typed, in the tooltip");

            // m marks missing, x excused, Delete clears, Ctrl+Z undoes.
            await press("ArrowDown");
            expect(selected(), "1,1", "second student, quiz");
            await press("m");
            expect(cell(1, 1).textContent.trim(), "M", "missing");
            await press("x");
            expect(cell(1, 1).textContent.trim(), "EX", "excused");
            await press("Delete");
            expect(cell(1, 1).textContent.trim(), "", "cleared");
            await press("z", { ctrlKey: true });
            expect(cell(1, 1).textContent.trim(), "EX", "undo");
            await press("z", { ctrlKey: true });
            expect(cell(1, 1).textContent.trim(), "M", "undo again");
            await press("y", { ctrlKey: true });
            expect(cell(1, 1).textContent.trim(), "EX", "redo");
            await saved();

            // n adds a note.
            await press("ArrowUp");
            await press("n");
            const prompt = await waitFor(".o_gradebook_prompt_input");
            prompt.value = "Retake";
            prompt.dispatchEvent(new Event("input", { bubbles: true }));
            prompt.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
            await waitFor(() => cell(0, 1).classList.contains("o_has_comment"), "comment mark");
            await saved();
        """)
        self.assertEqual(self._scores(self.lesson), {
            "Anna": ("scored", 88.0, False),
            "Ben": ("scored", 92.5, False),
        })
        self.assertEqual(self._scores(self.quiz), {
            "Anna": ("scored", 15.0, "Retake"),
            "Ben": ("excused", 0.0, False),
        })
        self.assertAlmostEqual(self.quiz.score_ids.filtered(lambda s: s.status == "scored").percent, 75)

    def test_paste_and_fill(self):
        self._run("""
            await waitFor("td.o_selected");
            await waitFor(() => document.activeElement.classList.contains("o_gradebook_scroll"), "grid focused");
            await press("ArrowLeft");
            // Paste a 2 x 2 block copied from a spreadsheet.
            const data = new DataTransfer();
            data.setData("text/plain", "81\\t12\\n\\tm\\n");
            document.activeElement.dispatchEvent(
                new ClipboardEvent("paste", { clipboardData: data, bubbles: true, cancelable: true }));
            await sleep(50);
            expect(cell(0, 0).textContent.trim(), "81", "pasted percent");
            expect(cell(0, 1).textContent.trim(), "60", "pasted points, shown as a percent");
            expect(cell(1, 0).textContent.trim(), "", "empty pasted cell left alone");
            expect(cell(1, 1).textContent.trim(), "M", "pasted missing");

            // Fill the column's empty cells.
            await press("F", { ctrlKey: true, shiftKey: true });
            const prompt = await waitFor(".o_gradebook_prompt_input");
            prompt.value = "100";
            prompt.dispatchEvent(new Event("input", { bubbles: true }));
            prompt.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
            await waitFor(() => cell(1, 0).textContent.trim() === "100", "filled");
            expect(cell(0, 0).textContent.trim(), "81", "fill keeps existing scores");
            await saved();

            // Enter can move right instead of down.
            document.querySelector(".o_gradebook_enter").click();
            await waitFor(() => /right/.test(document.querySelector(".o_gradebook_enter").textContent), "toggle");
            await waitFor(() => document.activeElement.classList.contains("o_gradebook_scroll"), "grid focused");
            await press("Enter");
            expect(selected(), "0,1", "Enter moves right");
            await sleep(300);
        """)
        self.assertEqual(self._scores(self.lesson), {
            "Anna": ("scored", 81.0, False),
            "Ben": ("scored", 100.0, False),
        })
        self.assertEqual(self._scores(self.quiz), {
            "Anna": ("scored", 12.0, False),
            "Ben": ("missing", 0.0, False),
        })
        self.assertEqual(self.ui_teacher.school_enter_direction, "right")

    def test_new_assignment_dialog(self):
        self._run("""
            await waitFor("td.o_selected");
            await waitFor(() => document.activeElement.classList.contains("o_gradebook_scroll"), "grid focused");
            await press("A", { ctrlKey: true, shiftKey: true });
            const name = await waitFor(".modal .o_field_widget[name='name'] input");
            name.value = "Extra Practice";
            name.dispatchEvent(new Event("input", { bubbles: true }));
            name.dispatchEvent(new Event("change", { bubbles: true }));
            document.querySelector(".modal .o_form_button_save").click();
            await waitFor(() => document.querySelectorAll("th.o_gradebook_assignment").length === 3, "new column");
            await waitFor(() => !document.querySelector(".modal"), "dialog closed");
            expect(document.querySelector("td.o_selected").dataset.col, "2", "new column selected");
        """)
        self.assertIn("Extra Practice", self.section_5.assignment_ids.mapped("name"))

    def test_office_is_read_only(self):
        new_test_user(
            self.env, login="grid_office", password="grid_office",
            groups="base.group_user,horizonforge_school_core.group_school_office",
        )
        self._run("""
            await waitFor("td.o_selected");
            await waitFor(".o_gradebook_bar .badge");
            if (document.querySelector(".o_gradebook_new")) { throw new Error("office can add assignments"); }
            await waitFor(() => document.activeElement.classList.contains("o_gradebook_scroll"), "grid focused");
            await press("5");
            await sleep(200);
            if (document.querySelector(".o_gradebook_editor")) { throw new Error("office can edit"); }
        """, login="grid_office")
        self.assertFalse(self.lesson.score_ids)

    def test_double_click_and_name_order(self):
        self.env["school.score"].create({
            "assignment_id": self.lesson.id, "student_id": self.anna.id, "value_entered": 90,
        })
        self.ben.first_name = "Aaron"
        self._run("""
            await waitFor("td.o_selected");
            const dblclick = (td) => td.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
            const names = () => [...document.querySelectorAll(".o_gradebook_student")].map((th) => th.textContent.trim()).join(" | ");
            expect(names(), "Example, Aaron | Example, Anna", "last name first");
            // Double-click a score: its comment. Double-click an empty cell: edit it.
            dblclick(cell(1, 0));
            const prompt = await waitFor(".o_gradebook_prompt_input");
            prompt.value = "Well done";
            prompt.dispatchEvent(new Event("input", { bubbles: true }));
            prompt.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
            await waitFor(() => cell(1, 0).classList.contains("o_has_comment"), "comment mark");
            await saved();
            dblclick(cell(0, 0));
            await waitFor(".o_gradebook_editor");
            await press("Escape");

            // Sort by first name: the selection stays on the same student.
            cell(1, 0).click();
            document.querySelector(".o_gradebook_name_order").click();
            await waitFor(() => names() === "Aaron Example | Anna Example", "first name first");
            await waitFor(() => /First Last/.test(document.querySelector(".o_gradebook_name_order").textContent), "label");
            expect(selected(), "1,0", "still on Anna");
        """)
        self.assertEqual(self.lesson.score_ids.comment, "Well done")
        self.assertEqual(self.ui_teacher.school_name_order, "first_last")

    def test_sidebar_opens_grid(self):
        """Gradebook in the School sidebar opens the grid in one click and
        lists the other gradebook screens under it."""
        code = HELPERS + """(async () => {
            const item = '.o_school_sidebar_item[data-menu-xmlid="horizonforge_school_gradebook.menu_school_gradebook_root"]';
            (await waitFor(item)).click();
            await waitFor(".o_school_gradebook", "gradebook grid");
            await waitFor(item + ".active", "Gradebook highlighted");
            await waitFor('.o_school_sidebar_subitem.active[data-menu-xmlid="horizonforge_school_gradebook.menu_school_gradebook"]',
                "grid listed under Gradebook");
            console.log("test successful");
        })().catch((e) => console.error(e.message));"""
        self.browser_js(
            "/odoo/action-horizonforge_school_core.school_student_action",
            code, login="grid_teacher", timeout=120,
        )

    def test_other_period_banner(self):
        today = fields.Date.context_today(self.env.user)
        if today.month == 12 and today.day == 31:
            self.skipTest("needs a day after today in the year")
        self.period.date_end = today
        self.env["school.period"].create({
            "year_id": self.year.id, "name": "Next",
            "date_start": fields.Date.add(today, days=1), "date_end": self.year.date_end,
        })
        self._run("""
            await waitFor("td.o_selected");
            if (document.querySelector(".o_gradebook_period_warning")) { throw new Error("banner on the current period"); }
            const select = document.querySelector(".o_gradebook_period");
            select.value = [...select.options].find((o) => o.text.trim() === "Next").value;
            select.dispatchEvent(new Event("change"));
            const banner = await waitFor(".o_gradebook_period_warning");
            expect(banner.textContent.includes("The current grading period is All Year"), true, "banner text");
            banner.querySelector("button").click();
            await waitFor(() => !document.querySelector(".o_gradebook_period_warning"), "banner gone");
            expect(document.querySelector(".o_gradebook_period").selectedOptions[0].text.trim(), "All Year", "period");
        """)

    def test_letters_missing_and_comments(self):
        essay = self.env["school.assignment"].create({
            "section_id": self.section_5.id, "name": "Essay", "date": self.lesson.date,
            "category_id": self.lesson.category_id.id, "entry_mode": "letter", "sequence": 3,
        })
        self._run("""
            await waitFor("td.o_selected");
            // A letter column: B starts a grade, its percent shows beside it.
            cell(0, 2).click();
            await press("b");
            await waitFor(".o_gradebook_editor");
            await press("Enter");
            await saved();
            expect(cell(0, 2).querySelector("sup").textContent, "89", "B's value");
            expect(cell(0, 2).textContent.trim().startsWith("B"), true, "the letter typed");
            // C is a grade here.
            await press("c");
            await waitFor(".o_gradebook_editor");
            await press("Enter");
            await saved();
            expect(cell(1, 2).textContent.trim().startsWith("C"), true, "C typed");
            // A missing score warns beside the name.
            cell(0, 0).click();
            await press("m");
            await waitFor(() => document.querySelectorAll(".o_gradebook_student")[0].querySelector(".o_gradebook_missing"), "warning");
            if (document.querySelectorAll(".o_gradebook_student")[1].querySelector(".o_gradebook_missing")) {
                throw new Error("warning on a student with nothing missing");
            }
            // Letters in every cell.
            cell(1, 0).click();
            await type("88");
            await press("Enter");
            await saved();
            if (cell(1, 0).querySelector("sup")) { throw new Error("letter shown before the toggle"); }
            document.querySelector(".o_gradebook_letters_toggle").click();
            await waitFor(() => cell(1, 0).querySelector("sup"), "letter beside the percent");
            expect(cell(1, 0).querySelector("sup").textContent, "B", "88 is a B");
            // The report card comment, from the Comments column.
            document.querySelector(".o_gradebook_comments_toggle").click();
            await waitFor("td.o_gradebook_comment");
            await waitFor(() => document.activeElement.classList.contains("o_gradebook_scroll"), "grid focused");
            await press("r");
            const area = await waitFor(".modal textarea");
            area.value = "Writes with care.";
            area.dispatchEvent(new Event("input"));
            document.querySelector(".modal-footer .btn-primary").click();
            await waitFor(() => [...document.querySelectorAll("td.o_gradebook_comment")].some((td) => td.textContent.includes("Writes with care.")), "comment shown");
        """)
        letters = {s.student_id.first_name: (s.letter_entered, s.percent) for s in essay.score_ids}
        self.assertEqual(letters, {"Anna": ("B", 89), "Ben": ("C", 81)})
        mark = self.env["school.period.mark"].search([("section_id", "=", self.section_5.id)])
        self.assertEqual(mark.comment, "Writes with care.")
        self.assertTrue(self.ui_teacher.school_cell_letters)

    def test_chart(self):
        self.env["school.score"].create([
            {"assignment_id": self.lesson.id, "student_id": self.anna.id, "value_entered": 90},
            {"assignment_id": self.lesson.id, "student_id": self.ben.id, "value_entered": 70},
        ])
        self._run("""
            await waitFor("td.o_selected");
            // Under the grid: the first student and the class average.
            await waitFor(".o_gradebook_chart polygon.o_average_area");
            expect(document.querySelector(".o_gradebook_chart_legend").textContent.includes("Example, Anna"), true, "legend");
            expect(document.querySelectorAll(".o_gradebook_chart circle.o_student_dot").length, 1, "Anna's one score");
            // A score typed shows at once.
            cell(0, 1).click();
            await type("15");
            await press("Enter");  // moves down to Ben: back to Anna
            cell(0, 1).click();
            await waitFor(() => document.querySelectorAll(".o_gradebook_chart circle.o_student_dot").length === 2, "second point");
            // Hover: the values of the assignment under the mouse.
            const svg = document.querySelector(".o_gradebook_chart svg");
            const box = svg.getBoundingClientRect();
            svg.dispatchEvent(new MouseEvent("mousemove", { clientX: box.left + 31, clientY: box.top + 50, bubbles: true }));
            const tip = await waitFor(".o_gradebook_chart_tip");
            expect(tip.textContent.includes("Lesson 1"), true, "tooltip names the assignment");
            expect(tip.textContent.includes("80"), true, "class average of 90 and 70");
            // The selected student's line follows the selection.
            cell(1, 0).click();
            await waitFor(() => document.querySelector(".o_gradebook_chart_legend").textContent.includes("Example, Ben"), "Ben");
            // Hide, and it stays hidden.
            document.querySelector(".o_gradebook_chart_toggle").click();
            await waitFor(() => !document.querySelector(".o_gradebook_chart"), "hidden");
            expect(localStorage.getItem("school_gradebook.hide_chart"), "1", "remembered");
            localStorage.removeItem("school_gradebook.hide_chart");
        """)
