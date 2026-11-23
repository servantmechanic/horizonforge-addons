# School Planner

Lesson planning for small schools on Odoo 19 Community: a pacing guide per
course, laid over the school calendar for each class. Installs on top of
`horizonforge_school_gradebook`. Classes without a guide work as before.

Planning lives in the **Planner** menu (Planner, Pacing Guides, Assignment
Schedules, Fill Ahead); the Gradebook menu is for grading.

## What it adds

| Record | Notes |
|---|---|
| Pacing guides | One per course: how many lessons, chapters with a test after each, when to finish, the days it meets; its place in the teacher's day |
| Pacing guide items | The guide's steps in teaching order: name (Lesson 23), unit, topic, category (none for a review day), class days it takes, points, entry mode, notes and files |
| Plan lines | A class's guide items on its days: date, completed or not, a date set by hand, the teacher's note for the day |
| No lessons | On a calendar entry shown only (a field trip, testing day): those it is for have no lesson that day |

## Pacing guides

Planner, **Pacing Guides** lists your courses' guides (My Courses; clear the
filter for all). **Drag them into the order your classes come each day**: the
planner and the weekly plan list each day's classes that way. Courses, Pacing
Guide opens a course's guide too, made the first time.

A guide is set up in a few numbers:

- **Lessons**: how many (160), their name and first number (Lesson 1), and
  their gradebook category.
- **Chapters and tests**: lessons per chapter (0 for none), a **test after
  each chapter** (its name, category and days: 0 for the same day as the
  chapter's last lesson, 2 for a long test), and a **review day** before it.
- **When**: finish by the end of the year, the end of a grading period, or a
  date. **One a day** gives each lesson a class day, with spare days at the
  end; **Spread out** gives lessons more days where there is room, to finish
  on the date. Nothing is doubled up by itself: when the items don't fit,
  the summary says how many won't, and you double them up (an item's Days
  at 0) or move the finish date.
- **Meets**: the weekdays the course meets (Science on Tuesday and Thursday).

The summary says how it fits: Needs 165 of the 176 class days to 05/21/2027:
11 spare · 165 items. Or, when it doesn't: Needs 180 class days, 176 to
05/21/2027: 4 won't fit · double up 4 (Days 0) or finish later.

**Build Guide** makes the items. Building again (after changing a number)
keeps the items of the same name with their notes, files and gradebook
columns, removes the ones no longer wanted (unless a gradebook column uses
them), and leaves items added by hand where they are. **Items** opens the full
list: add notes or files (the quiz to print), insert an extra test or a
review day, or drag to reorder. **Days** on an item is the class days it takes
(0: the same day as the item before).

**Export / Import** downloads the guide's items as a CSV, or as a zip with the
CSV and the files, and imports one into a course (after its items, or
replacing them). A CSV needs only a Name column; it can also have Order,
Unit, Topic, Category (code or name), Days, Max Points, Entry Mode, Notes and
Files. Duplicating a course copies its guide and its settings: Math 2 becomes
Math 3.

## The plan

Each class's plan lays its course's guide over its **class days**: school
days on the guide's meeting weekdays, without days off and without the
calendar entries marked **No lessons** for the class (everyone, its grade
levels, its homeroom or its teacher).

- **Completed** items keep the day they were done. An item is completed once
  its gradebook column has scores or its day has passed; the items before the
  last one completed count too. Nothing to mark done.
- The rest follow from the next class day, so a class that falls behind
  moves its plan along by itself, and a snow day or field trip pushes it a day.
- A **date set by hand** (in the planner's list, or by dragging in its
  calendar) holds, and what comes after follows it; Let the Plan Place It
  undoes it. A gradebook column made ahead holds its date the same way, and
  moving the column's date moves the plan.
- A guide started mid-year finds the gradebook columns already made under
  the same names, so its settings should match what the class has done
  (a test every 5 lessons, say).

Planner, **Planner** shows your classes' plans on a calendar (month, week or
day: whole days, no hours; each day's classes in your order) or as a list,
one class at a time. Click a lesson for its notes, to add a note for the day,
or to change its date. **Weekly Plan** above it prints the week.

**Progress** shows on Classes and at the top of the gradebook: the last item
completed, how many there are, and how far ahead or behind the class is
against the guide started on the year's first class day (Lesson 62 of 170 ·
3 behind), and how many days short of the year the rest would run.

## The gradebook

With a guide, the gradebook's next column (Tab past the last column, the +
column, or a key in an empty period) is the guide's **next item** that needs
a column: its name, category, points and entry mode. A category's key asks
for the next item of that category (`-`: the next test). A column made as a
lesson that changes to a test becomes the guide's next test.

**Fill ahead** in the grid makes the columns of this week's graded items, on
their planned days. Without a guide it fills the grading period from the
course's weekday schedule, as before.

## Schedules and Fill Ahead

The gradebook's **Assignment Schedules** (what repeats on fixed weekdays: a
spelling test every Friday) and **Fill Ahead** (many classes at once) are
under Planner. Fill Ahead fills a class with a guide from its plan (this
week's lessons), and a class with a schedule from the schedule (the grading
period). Uninstalling the planner puts them back under Gradebook.

## Weekly plan

**Weekly Plan** (above the planner) prints a landscape page per teacher and
week (one or more weeks): Monday to Friday across, the classes down in the
teacher's order, each day's items with their topic, the guide's notes and
the day's note. Days off and calendar events show under each day. The office
can print any teacher's.

## Access

- **Teacher**: reads every guide, sets up and changes the guides of the
  courses they teach, and plans their own classes.
- **Office**: reads every class's plan.
- **Principal**: everything.

## Demo data

With demo data, the reference school's Math courses (150 lessons, a test
every 10) and Science courses (Tuesday and
Thursday, 60 lessons, a quiz every 6) get guides, built from those settings;
the gradebook demo's columns of the same names count as completed. On a
database without demo data, after loading the gradebook demo:

```python
env["school.year"]._load_school_planner_demo()
env.cr.commit()
```

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_school_planner \
    -i horizonforge_school_planner --test-tags /horizonforge_school_planner --stop-after-init
```
