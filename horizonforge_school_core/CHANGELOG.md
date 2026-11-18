# School addons changelog

One version covers all the school addons (`horizonforge_school_core`,
`_gradebook`, `_attendance`, `_documents`): every release sets the same
version in all four manifests, as `19.0.MAJOR.MINOR.PATCH`, even when a module
has no changes. The version is shown at the foot of the School sidebar.

- **MINOR**: new screens, settings or records (needs a module upgrade).
- **PATCH**: fixes only.
- **MAJOR** stays 0 until the first school runs on it in production.

Each release is tagged in git as `school-<version>`, for example `school-0.7.0`.

## 0.7.0 (2026-11-18)

- **Sidebar.** On wide screens the School menus are in a sidebar, each one
  click away: Gradebook opens the grid and Attendance opens the daily grid,
  with the other screens of the section listed under it. The top-bar menus are
  hidden while the sidebar is shown; phones keep Odoo's menu.
- **Version shown.** The sidebar shows the installed version.
- **Simple interface on the demo.** The demo data turns on the simple
  interface of `horizonforge_ce_custom`: teachers and office staff no longer
  see Discuss, Contacts, Apps, the chat and activity icons, or OdooBot.
- **Filters by grade and grading period.** Absences & Tardies and
  Assignments filter by Today, This Week, Current Grading Period and Current
  Year, and group by Grade Level, Grading Period and Homeroom. Assignments
  also have an Upcoming filter and group by Course. Odoo's date filter, which offered calendar quarters
  (Q1 to Q4) instead of the school's grading periods, is gone. Attendance lines
  keep the student's grade level from the day they were recorded, so last
  year's absences stay under last year's grade.
- **Side panels.** Assignments, Absences & Tardies and Letter Grades &
  Comments have a panel of grading periods, grade levels and classes (or
  categories, homerooms, codes) to pick from with one click. They open on the
  current grading period, and on My Classes (My Homeroom) for teachers; every
  choice can be cleared and picked again.
- **Current and Previous Grading Period** filters, **Not Fully Scored** for
  assignments dated today or earlier with students still to score (a To Score
  column shows how many), **My Classes** on Letter Grades and Enrollments,
  **My Students** on Students, **My Courses** on Assignment Schedules.
- Absences keep the homeroom as well as the grade level from the day they were
  recorded; who may see them still follows the student's current homeroom.
- **Every teacher sees every student** and their patrons, notes and files
  (before: only students in their own classes). Classes, enrollments, grades
  and attendance stay limited to the teacher's own.
- School is the first app, so school users land on it after login.

## 0.6.0 (2026-11-16)

Before 0.7.0 each module had its own version (core 0.4.1, gradebook 0.6.0,
attendance 0.2.0, documents 0.1.0). Together they held:

- **Core:** school years with grading periods ending on Fridays, a school
  calendar with days off and holidays shown for information, grade levels,
  homerooms, students and patrons, courses, classes and enrollments. Classes
  are generated from the homerooms; New Year Setup creates the next year,
  promotes students and enrolls them; the Setup Guide lists the steps.
- **Gradebook:** score categories, weight schemes, grading scales, and
  assignment schedules that generate a grading period of assignments (every N
  weeks, moved off days off, or kept as templates for tests placed by hand).
  A keyboard grid with batched autosave, undo, paste and a live grade column.
  One grade engine for the grid, PDF reports and CSV exports; courses graded by
  letter or comment only.
- **Attendance:** once a day by homeroom, present unless an absence, part day
  or tardy is recorded, in a keyboard grid with running totals per grading
  period. Attendance summary report; totals on the report card.
- **Documents:** schoolwide folders, a folder per year and homeroom, files on
  the student record, and two-step delete (trash, then the office erases).
