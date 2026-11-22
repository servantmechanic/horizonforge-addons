# Ozark Timecard Report

A printable timecard for Odoo 19 Community, from the Attendances app: hours
worked, weekly overtime, pay and paid time off, for a pay period.

## Use

Attendances, **Timecards** (or **Print Timecard** in the Actions menu of
selected employees) opens the wizard:

| Option | Default |
|---|---|
| Employees | Empty: every active employee with hours or time off in the period |
| From / To | The last two weeks |
| Report style | Summary and detailed timecards, the payroll summary only, or the detailed timecards only |
| OT threshold | 40 hours a week |
| OT multiplier | 1.5 |
| Week starts on | Sunday (overtime is counted per workweek) |

- **Pay** uses the hourly rate from the employee's Payroll tab (the Wage field
  on Community). An employee without a rate is flagged on the report.
- **Time off** taken in the period is paid at the regular rate when its time
  off type is marked **Paid (Timecard)** (on by default; uncheck it for unpaid
  leave types).
- Hours are shown in each employee's time zone.

## Requirements

Depends on `hr_attendance` and `hr_holidays` (core Odoo).
