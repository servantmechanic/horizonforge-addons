# School addons changelog

One version covers all the school addons (`horizonforge_school_core`,
`_gradebook`, `_attendance`, `_documents`, `_planner`): every release sets
the same version in all their manifests, as `19.0.MAJOR.MINOR.PATCH`, even when a module
has no changes. The version is shown at the foot of the School sidebar.

- **MINOR**: new screens, settings or records (needs a module upgrade).
- **PATCH**: fixes only.
- **MAJOR** stays 0 until the first school runs on it in production.

Each release is tagged in git as `school-<version>`, for example `school-0.7.0`.

## Unreleased

- **Principal.** The school's top access level, Administrator, is now
  Principal: everything school (students, patrons, classes, grading weights
  and scales, locked grades), exporting data, and a School Settings screen
  (Configuration) with every school setting, without Odoo's own settings
  (users, apps, email), which stay with the system administrator.

- **Lesson (L).** The shipped score category Lesson/Homework (HW) is now
  Lesson (L); an upgrade renames it once, unless the school renamed it.
- **My Courses.** Pacing Guides and Assignment Schedules open on the
  teacher's own courses.

- **New addon: School Planner** (`horizonforge_school_planner`). A pacing
  guide per course, set up in a few numbers (how many lessons, chapters with
  a test and review day after each, finish by a date or the end of a period
  or the year, one a day or spread out, the days it meets; what won't fit
  is shown, never doubled up by itself) and built into
  its items (with notes and files; items added by hand stay when it is built
  again), imported and exported as CSV or as a zip with the files. The
  guides' order is each teacher's order of classes in the day. Each class's plan lays it over its days
  (the course's meeting weekdays, without days off and calendar entries
  marked No lessons for it): taught items keep their day, the rest follow
  on, and a date set by hand holds. An item is taught once its gradebook
  column has scores or its day has passed; nothing to mark done. Progress
  (Lesson 62 of 170, 3 behind) shows on the classes and in the gradebook.
  The planner shows whole days (no hours) and has the Weekly Plan button.
  The gradebook's next column (Tab, +, a key) is the guide's next item, and
  Fill ahead makes this week's columns from the plan (or, without a guide,
  the period's from the schedule, as Generate did). A weekly plan prints a
  page per teacher and week, with the guide's notes and day notes.
  Planning lives in the Planner menu, grading in the Gradebook: Assignment
  Schedules and Fill Ahead (formerly Generate Assignments; it now fills
  from a guide too) move to Planner when the planner is installed.

- **Add assignments as you go.** In the gradebook, Tab past the last column
  (once it has a score) adds the next assignment on the next school day,
  named after the last of its kind (Lesson 13), as in Candle. A score
  category's shortcut key (`/` lesson, `-` test) makes the column you're on
  that category; the keys show in the top bar. A preference turns Tab's
  new column off. A + column at the end adds the next assignment, and an
  empty grading period starts with a key (`/`, `-`, Tab, Enter or a score),
  numbering on from the period before: no schedule needed.
- **Notes and files on assignments.** An assignment holds notes and files
  (the quiz to print); the column header marks them, and Assignments, With
  Files lists them.

- **Student vs class average graph.** Under the gradebook grid, a graph of
  the selected student's score on each assignment beside the class average,
  with the values on hover; it follows the selected row and updates as you
  type. A new Class Performance report prints the same graph for every
  student, one page per class, for one or several grade levels and subjects.

- **Letter grades per assignment.** An assignment can be entered as letters
  (an essay graded A-): each letter counts as the grading scale's value for
  it, by default the middle of its range and 5 below the top for the lowest
  letter (F counts 65), editable per scale line. The student's own scale
  applies, so the lower grades' scale gives its own values.
- **Letter courses in the gradebook.** Courses graded by letters (PE) now use
  the grid like any other, typed as letters by default; their period and year
  grades show and print as a letter only, averaged from the scores. The
  period letter typed once per grading period is gone (existing ones are not
  carried over).
- **n for a note.** In the gradebook, `n` (not `c`) adds a note to a score,
  as in the attendance grid; double-click still works.
- **Report card comments in the grid.** A Comments column (or `r` on a
  student) writes the report card comment. Letter Grades & Comments is now
  Report Card Comments, comments only.
- **Cells show percents.** Points and number-wrong scores show the percent
  (what was typed is in the tooltip and on F2); letters show their percent
  beside them; a Letters switch (and preference) adds the letter beside every
  score. A ⚠ beside a student flags a missing score in the period.

- **Teachers keep the calendar.** Every teacher sees School, Calendar and can
  add, change or remove entries (a snow day, a field trip). An entry shown
  only can be for everyone or only for some grade levels, homerooms or
  teachers; the calendar opens on the entries for you (For Me filter), and
  the printed calendar names who an entry is for. Days without school stay
  for everyone.
- **School days sets the last day.** A school year can have a number of
  school days (180) and planned snow days (5): the end date then follows from
  the start date, the weekends and the days off. Marking a day off as a snow
  day uses up a planned one; only once they run out does the last day move
  later. The last grading period moves with it. New Year Setup copies both
  numbers but not last year's snow days.
- **Homeroom teachers keep their students' grades.** A homeroom teacher
  enters and changes the grades of their homeroom's students in every class
  they take, beside the class's own teacher (science, music): those classes
  are in their gradebook and under My Classes, showing only their own
  students, and the report card they print has every subject.
- **My Preferences.** School, My Preferences (and the School part of Odoo's
  own Preferences dialog): student name order and where Enter moves in the
  gradebook. School settings, Teacher Preferences, set the defaults for new
  users.
- **Other grading period warning.** The gradebook shows a banner when the
  grading period on screen isn't the current one, with a button back to it.
- **Duplicate a course.** Duplicating a course (Math 2 into Math 3) copies its
  grade levels, teacher and assignment schedules; the code is left empty.

- **Attendance notes by double-click.** Double-clicking a recorded absence or
  tardy in the attendance grid opens its note, like the N key.
- **Print the school calendar.** The School Calendar has a Print button, and
  each school year a Print Calendar button: a one-page PDF of the year at a
  glance, with days off shaded red, days shown only in blue, the first and
  last days and grading period ends outlined, school days per month, and the
  lists of days off and grading periods.
- **New report card.** The report card is now a folded card, two landscape
  pages per student: parent signature and teacher comments on the back, a
  cover with the student, school, a verse or motto and a letter to parents,
  and inside the grades for every grading period with the year average, the
  grading scale's key, conduct traits with blank boxes to mark by hand, and
  attendance. The cover texts and conduct traits are School settings; grading
  scale lines get a description for the key. It replaces the report card sheet.
- **Report card reference.** A new grade report, one page per homeroom, for
  copying grades onto a separate paper card: each student's period grade in
  every subject, the year grade so far, absences and days present.
- **Printing works for teachers and office staff.** Report cards, class
  sheets and the attendance summary failed for users who aren't system
  admins (they can't read report actions).

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
