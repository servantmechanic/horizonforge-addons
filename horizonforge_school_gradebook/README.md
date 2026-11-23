# School Gradebook

A keyboard-driven gradebook for small schools on Odoo 19 Community. Installs on
top of `horizonforge_school_core`.

## What it adds

| Record | Notes |
|---|---|
| Score categories | Name, short code, color and shortcut key. Ships with Lesson (L, `/`) and Test (T, `-`) |
| Weight schemes | Category weights that total 100, and the calculation method |
| Grading scales | Letter, lowest percent, value when entered and GPA points. Several scales are allowed |
| Assignment schedules | Per course: which assignments fall on which weekdays |
| Assignments | A gradebook column: class, date, category, max points, entry mode, notes and files |
| Scores | What the teacher typed (a number or a letter), the percent, and a status (scored, excused, missing) |
| Report card comments | Per student, class and grading period: the comment printed on the report card |

Settings resolve from most specific to least: class, then course, then school
(Configuration, Settings). Ships with a letter scale (A to F) and an example
scale for the lower grades (E/S/N/U), to set on those grade levels.

## Letters

Any assignment can be entered as **letters** (entry mode Letter): an essay
graded A-, say. A letter counts as its **value when entered** on the student's
grading scale, so a lower grade on its own scale (A from 97) counts by that
scale. By default the value is the middle of the letter's range (A from 93 to
100 counts 96.5, B 89); the lowest letter counts 5 below the top of its range
(F counts 65, not 30). Change the values per scale line under Configuration,
Grading Scales; scores already typed follow. Averages then work as usual.

A course is graded by **scores and percent** (the default), by **letters**
(PE, art) or by **comment only** (conduct). A letters course is in the grid
like any other, its assignments typed as letters by default, and its period
and year grades are shown and printed as a letter only. Comment-only courses
stay out of the grid.

## Report card comments

Every class can have a comment per student and grading period, printed on the
report card. Write them in the grid (the **Comments** column, or `r` on a
student), or under Gradebook, **Report Card Comments**: one grading period,
every class of yours grouped, a line per student.

## The grid

School, Gradebook opens the grid: students down the side, the grading period's
assignments across the top, on today's column. Every cell is saved as you
leave it. Press `?` in the grid for the full shortcut list.

| Key | Action |
|---|---|
| Type a number | Enter a score, replacing what is there |
| Enter / Shift+Enter | Save and move to the next / previous student |
| Tab / Shift+Tab | Save and move right / left. Past the last column, once it has a score: the next assignment |
| `/`, `-` (a category's key) | Make the column that category; in an empty period, start with one |
| F2 | Edit the cell, keeping its value |
| x, m, Delete | Excused, missing, clear |
| n, or double-click a score | The score's note (n, as in the attendance grid) |
| A, B, ... in a letter column | A letter grade. Where N is a grade (E/S/N/U), double-click for the note |
| r | The student's report card comment |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+Shift+A | New assignment |
| Ctrl+Shift+F | Fill the column's empty cells |
| Ctrl+V | Paste a column or block from a spreadsheet |

**Adding assignments as you go** (as in Candle): Tab past the last column,
once it has a score, adds the next assignment on the next school day: same
category, points and entry mode as the last of its kind, named after it
(Lesson 13 after Lesson 12). Press a category's key (`/` lesson, `-` test,
set under Configuration, Score Categories) to make the column you're on that
category; a name the grid gave it follows (Lesson 13 becomes Test 5). The top
bar shows the keys. Turn it off in My Preferences (Gradebook: Tab Adds an
Assignment). Tests can come whenever a section ends: nothing has to be
scheduled.

The **+** column at the end adds the next assignment too, with or without
scores. An empty grading period starts from the keyboard: a category's key
(`/`, `-`) adds a first assignment of that category, Tab or Enter one of the
class's usual category, and typing a score adds one and enters it. The first
assignment of a period goes on its first school day (or the next school day
from today, once it has started), and its name goes on from the period
before (Lesson 41 after Lesson 40). A class with no schedule and no pacing
needs nothing set up: it starts with Lesson 1.

**Notes and files**: an assignment's form (click its column header) holds
notes and files, such as the quiz to print or its answer key. The header
shows a note or paperclip mark; Assignments, With Files finds them all.
Whoever can see the assignment can open its files.

When the grading period on screen isn't the current one, a banner says so,
with a button back to the current period. It shows once, never per entry.

Entry modes: percent (type 88), points (type 22 of 25), number wrong (type 3
of 25) or letter (type B+). The typed value is kept, so changing an
assignment's max points recalculates the percent without retyping.

Cells show percents: points and number wrong show the percent they make (the
typed value is in the tooltip, and comes back with F2). A letter shows with
its percent beside it. **Letters** in the top bar (or My Preferences) adds the
letter beside every score. A ⚠ beside a name means a score marked missing in
the grading period.

Under the grid, a **graph** shows the selected student's score on each
assignment (blue) beside the class average (gray), numbered as the columns;
hover for the values. It follows the row you're on and changes as you type.
**Hide graph** folds it away (remembered on that computer). Scores count as in
the averages: excused work is left out, missing work counts 0 when the school
counts it so. The printed Class Performance report draws the same chart for
every student.

## Assignment schedules

Under Gradebook, Assignment Schedules (Planner, Assignment Schedules when
School Planner is installed: planning lives there), say what each course has every
week, for example:

| Course | Assignment | Category | Days |
|---|---|---|---|
| Math 5 | Lesson | HW | Mon to Fri |
| Spelling 5 | Spelling Test | T | Fri |
| English 5 | Lesson | HW | Mon, Wed, Fri |

A schedule doesn't have to run every week: **Every (Weeks)** set to 3 with
**First Week** 3 gives a test on the chosen weekday in school weeks 3, 6, 9 and
so on. Weeks without any school day aren't counted.

**Fill ahead** in the grid (one class), or Fill Ahead in the menu (many
classes; under Planner with School Planner), creates the whole grading period at once and
numbers the assignments through the year (Lesson 1, Lesson 2, ...). It leaves
existing assignments alone, so it is safe to run again.

When an assignment's day is a day off, it moves to the next school day (or the
one before, at the end of a grading period), unless that day already has the
same schedule's assignment: a Friday test moves to Monday, while a daily
lesson is simply dropped. Clear **Move If Day Off** on a schedule to skip it
instead. After the calendar changes, generating again moves the scheduled
assignments that have no scores yet.

**Tests placed by hand:** leave every weekday off. The schedule then generates
nothing; choose it under **From Schedule** when adding an assignment in the
grid, and the name (Test 4), category, points and entry mode are filled in.

Schedules belong to the course, so next year's classes use
them without any copying. Duplicating a course copies its schedules.

## Access

- **Teacher**: assignments and scores of their own classes, and the assignment
  schedules of the courses they teach. A homeroom teacher also keeps their
  homeroom's students' grades in every class they take, beside the class's
  own teacher: those classes are in their gradebook, showing only their own
  students.
- **Office**: reads every class's gradebook.
- **Administrator**: everything, including scores in locked grading periods.

## Grades

One calculation engine (`school.grade.engine`) produces every grade: the grid,
the reports and the CSV exports always agree.

- **Category average**: the mean of the percents, or total points earned over
  points possible, by the weight scheme's method.
- **Period grade**: the weighted average of the category averages. A category
  without scores gives its weight to the others.
- **Statuses**: excused scores and empty cells never count. Missing scores
  count as 0 or are left out, by setting.
- **Rounding**: half up to the grade decimals (0 by default: 92.5 becomes 93),
  then the letter is looked up on the rounded grade.
- **Year grade**: the average of the period grades, or cumulative over all the
  year's scores, by setting.

Worked example with the shipped defaults: homework 90, 80, 100 averages 90;
tests 84 and 76 average 80; the period grade is (50 x 90 + 50 x 80) / 100 = 85, a B.

In the grid, the **Grade** column beside the names shows each student's period
grade and letter, and its header the class average. It updates as scores are
typed. **Category averages** in the top bar adds one column per category.

## Reports

School, Reports prints a PDF or exports the same data as CSV.

| Report | Contents |
|---|---|
| Report card | The folded card, two Letter landscape pages per student (print both sides, fold in half). Outside: parent signature and the period's teacher comments on the back; the cover with the student, grade level, school year, school logo and name, a verse or motto and a letter to parents. Inside: every graded subject with its grade for each period so far (later periods blank) and the year average, the key of the grading scale, the conduct traits with empty boxes to fill in by hand, and attendance (absences and days present). Pick a homeroom or grade level to print a whole group in one PDF |
| Report card reference | One page per homeroom, a table per grade level, for copying grades onto a paper card: each student's period grade in every subject with the year grade so far under it, and absences and days present |
| Class grade sheet | One page per class: each student's category averages, period grade and letter, and the class average |
| Progress report | One page per student and class: every assignment with its score, then the averages |
| Missing work | Students with work marked missing, by class, for a period or the whole year |
| Class performance | One page per class: a chart per student of their score on each assignment of the period (blue) beside the class average (gray), with their period grade. Choose one or several grade levels and subjects, or all |

Teachers get their own classes; the office and administrators every class.
The header uses the company's name, address and logo, and the principal's
name from the settings. School settings, Reports, holds the report card's
verse or motto, letter to parents and conduct traits (a heading per line,
then its traits starting with a dash). A grading scale line's description
(for example Excellent Work) prints in the card's key.

## Demo data

With demo data, the reference school gets schedules, the started quarters'
assignments and random scores up to today. On a database without demo data,
after loading the core demo (see the core README):

```python
env["school.year"]._load_school_gradebook_demo()
env.cr.commit()
```

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_school_gradebook \
    -i horizonforge_school_gradebook --test-tags /horizonforge_school_gradebook --stop-after-init
```

The grid's browser tests need Chrome and `websocket-client`; without them they are skipped.
