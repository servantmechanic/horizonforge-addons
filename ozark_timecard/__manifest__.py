{
    "name": "Ozark Timecard Report",
    "version": "19.0.2.1.0",
    "category": "Human Resources",
    "summary": "Printable timecard: attendance hours, weekly overtime, pay, and time off",
    "author": "Ozark AG LLC",
    "license": "AGPL-3",
    "depends": ["hr_attendance", "hr_holidays"],
    "data": [
        "security/ir.model.access.csv",
        "views/hr_leave_type_views.xml",
        "wizard/timecard_wizard_views.xml",
        "report/timecard_report.xml",
        "report/timecard_templates.xml",
    ],
    "installable": True,
    "application": False,
}
