{
    "name": "School Attendance",
    "version": "19.0.0.2.0",
    "category": "School",
    "summary": "Daily attendance for small schools: students are present unless "
               "an absence, part day or tardy is recorded, in a keyboard grid",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Attendance for the school addons. See README.md.",
    "author": "Ozark AG LLC",
    "license": "LGPL-3",
    "depends": ["horizonforge_school_core", "web"],
    "data": [
        "security/school_attendance_security.xml",
        "security/ir.model.access.csv",
        "data/school_attendance_data.xml",
        "views/school_attendance_views.xml",
        "wizard/school_attendance_report_views.xml",
        "wizard/school_setup_guide_views.xml",
        "report/school_attendance_reports.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/school_attendance_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "horizonforge_school_attendance/static/src/attendance/*",
        ],
    },
    "installable": True,
}
