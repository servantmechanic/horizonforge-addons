# School Gradebook

A keyboard-driven gradebook for small schools on Odoo 19 Community. Installs on
top of `horizonforge_school_core`.

## What it adds

| Record | Notes |
|---|---|
| Score categories | Name, short code and color. Ships with Lesson/Homework (HW) and Test (T) |
| Weight schemes | Category weights that total 100, and the calculation method |
| Grading scales | Letter, lowest percent and GPA points. Several scales are allowed |
| Assignment schedules | Per course: which assignments fall on which weekdays |
| Assignments | A gradebook column: class, date, category, max points, entry mode |
| Scores | What the teacher typed, the percent, and a status (scored, excused, missing) |
| Letter grades and comments | Per student, class and grading period: the letter of a letter-only course, and a comment for the report card |

Settings resolve from most specific to least: class, then course, then school
(Configuration, Settings). Ships with a letter scale (A to F) and an example
scale for the lower grades (E/S/N/U), to set on those grade levels.

## Courses without scores

A course is graded by scores and percent (the default), by letter only (PE,
say) or by comment only. Letter-only and comment-only courses stay out of the
grid: Gradebook, Letter Grades & Comments lists every student per class and
grading period to fill in. Any course can have a comment there; comments print
on the report card.

## The grid

School, Gradebook opens the grid: students down the side, the grading period's
assignments across the top, on today's column. Every cell is saved as you
leave it. Press `?` in the grid for the full shortcut list.

| Key | Action |
|---|---|
| Type a number | Enter a score, replacing what is there |
| Enter / Shift+Enter | Save and move to the next / previous student |
| Tab / Shift+Tab | Save and move right / left |
| F2 | Edit the cell, keeping its value |
| x, m, Delete | Excused, missing, clear |
| c, or double-click a score | Comment |
| Ctrl+Z / Ctrl+Y | Undo / redo |
| Ctrl+Shift+A | New assignment |
| Ctrl+Shift+F | Fill the column's empty cells |
| Ctrl+V | Paste a column or block from a spreadsheet |

Entry modes: percent (type 88), points (type 22 of 25) or number wrong (type 3
of 25). The typed value is kept, so changing an assignment's max points
recalculates the percent without retyping.

## Assignment schedules

Under Gradebook, Assignment Schedules, say what each course has every
week, for example:

| Course | Assignment | Category | Days |
|---|---|---|---|
| Math 5 | Lesson | HW | Mon to Fri |
| Spelling 5 | Spelling Test | T | Fri |
| English 5 | Lesson | HW | Mon, Wed, Fri |

A schedule doesn't have to run every week: **Every (Weeks)** set to 3 with
**First Week** 3 gives a test on the chosen weekday in school weeks 3, 6, 9 and
so on. Weeks without any school day aren't counted.

**Generate from schedule** in the grid (one class), or Gradebook, Generate
Assignments (many classes), creates the whole grading period at once and
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
them without any copying.

## Access

- **Teacher**: assignments and scores of their own classes, and the assignment
  schedules of the courses they teach.
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
