# School Attendance

Daily attendance for small schools on Odoo 19 Community. Installs on top of
`horizonforge_school_core`; works with or without the gradebook.

## How it works

Attendance is taken once a day, by homeroom. **Every student is present
unless something is recorded**, so the teacher only enters the exceptions.

| Code | Meaning | Counts as |
|---|---|---|
| A | Absent | 1 day absent |
| E | Excused absence | 1 day absent, excused |
| H | Part day absent | 0.5 day absent |
| X | Part day excused | 0.5 day absent, excused |
| T | Tardy | A tardy, not an absence |

The codes are the shipped starting values: change them, their letters and how
much of a day they count under Configuration, Attendance Codes.

## The grid

School, Attendance opens the teacher's homeroom on this week, with today's
column selected. Weekends are left out and the school calendar's days off are
greyed.

| Key | Action |
|---|---|
| A code's letter (A, E, H, X, T) | Record it on the selected student and day |
| Delete, Backspace or Space | Clear it: the student was present |
| n | Add a note to what is recorded |
| Arrows, Tab, Enter | Move |
| Ctrl+Z / Ctrl+Y | Undo / redo |

The two columns beside the names show each student's days absent and tardies
for the grading period, and follow every change. **Grading period** shows the
whole period instead of one week.

## Access

- **Teacher**: the students of the homeroom they teach.
- **Office**: every student.
- **Administrator**: also days in locked grading periods.

## Reports

- **Attendance Summary** (Attendance menu): per student, school days, days
  present, absent, excused, unexcused and tardies, for a grading period or any
  dates, as PDF or CSV. School days are counted up to today.
- **Absences & Tardies**: the list of everything recorded, to filter and group.
- With the gradebook installed, the **report card** shows absences and days
  present per grading period and for the year, and so does the report card
  reference.

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_school_attendance \
    -i horizonforge_school_attendance --test-tags /horizonforge_school_attendance --stop-after-init
```
