# School Core

Base records for a small school on Odoo 19 Community. It is the first of three
addons: the gradebook and attendance addons install on top of it.

## What it holds

| Record | Notes |
|---|---|
| School years | One year is marked current at a time |
| Grading periods | Any number per year (quarters, trimesters, six weeks); can be locked |
| Grade levels | Ordered, lowest first |
| Homerooms | A room with its teacher and grade levels (for example Lower Room and Upper Room); the year's classes are generated from them |
| School calendar | Days off (holidays and breaks) and holidays shown for information; the office can change it any time, in a calendar or a list |
| Students | Each student has a contact record for address, phone and email |
| Patrons | Contacts flagged as a family contact, linked to their students |
| Courses | A subject for one group, such as Math 5 |
| Classes | A course taught by a teacher in one school year |
| Enrollments | A student in a class, with dates for mid-year moves |

## Groups

- **Teacher**: reads every student and patron (a small school, where
  everyone knows everyone), and their own classes (as teacher or co-teacher)
  with their enrollments, grades and attendance.
- **Office**: reads every class, and manages students, patrons and enrollments.
- **Administrator**: manages years, grading periods, grade levels, homerooms,
  courses, classes and settings.

## Setup order

Configuration, **Setup Guide** lists the steps with what is done so far; each
step opens the normal screen:

1. School year and grading periods. New Year Setup can generate equal periods
   that each end on a Friday (six by default).
2. School calendar: holidays and breaks (School, School Calendar).
3. Grade levels, lowest first.
4. Homerooms: each room with its teacher and grade levels.
5. Courses, each with its grade levels. A course taught by someone other than
   the homeroom teacher (music, say) names its own teacher.
6. Students: by hand, or import the CSV template (Actions, Import records).
   Patrons named in the import must exist first. A student's homeroom follows
   their grade level.
7. Classes: **Generate** creates one class per course of each homeroom's grade
   levels and enrolls every student in the courses of their own grade level.
   Safe to run again after adding courses or students.

## School calendar

A calendar day is either **No school** (a day off: no assignments, no
attendance) or **Shown only** (on the calendar for information, school is in
session). Good Friday, Easter, Thanksgiving and Christmas are added to every
new year as shown only; switch one to No school to make it a day off. **Add
Holidays** on the school year adds them to a year that doesn't have them.

## Names and contacts

Students and patrons are contacts underneath, but the school screens show only
what a school needs: no sales, purchase or accounting fields. The addon needs
only Odoo's base, so it runs on its own or beside other apps. In the gradebook
and attendance grids, each user chooses whether students are listed last name
first or first name first.

## A new school year

Configuration, New Year Setup creates next year in one step: the year and its
grading periods and days off on the same weekdays as last year, last year's classes (or
classes generated from the homerooms), students moved up one grade level with
the top grade archived, and everyone enrolled in their new classes.

## Sidebar and version

On wide screens the School menus show in a sidebar, one click each (Gradebook
opens the grid, Attendance the daily grid). Phones keep Odoo's menu. The foot
of the sidebar shows the version of the school addons, which all share one
version: see [CHANGELOG.md](CHANGELOG.md).

## Demo data

The demo data builds a made-up reference school: 10 grade levels, 5
homerooms, 5 teachers (`teacher1` to `teacher5`, password `teacher`), 60 students and
40 classes. It also turns on the simple interface of `horizonforge_ce_custom`
(no Discuss, Contacts or Apps for non-administrators). On a database created without demo data, load it from the shell:

```python
env["school.year"]._load_school_demo()
env.cr.commit()
```

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_school_core \
    -i horizonforge_school_core --test-tags /horizonforge_school_core --stop-after-init
```
