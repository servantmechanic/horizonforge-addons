{
    "name": "School Core",
    "version": "19.0.0.7.0",
    "category": "School",
    "summary": "School records for small schools: years, grading periods, "
               "grade levels, homerooms, students, patrons, courses, classes, enrollments",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Base records for the school addons. See README.md.",
    "author": "Ozark AG LLC",
    "license": "LGPL-3",
    "depends": ["base", "web"],
    "data": [
        "security/school_security.xml",
        "security/ir.model.access.csv",
        "views/school_year_views.xml",
        "views/school_grade_level_views.xml",
        "views/school_homeroom_views.xml",
        "views/school_course_views.xml",
        "views/school_section_views.xml",
        "views/school_enrollment_views.xml",
        "views/school_student_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/res_users_views.xml",
        "wizard/school_year_setup_views.xml",
        "wizard/school_setup_guide_views.xml",
        "views/menus.xml",
        "report/school_calendar_report.xml",
    ],
    "demo": [
        "demo/school_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "horizonforge_school_core/static/src/sidebar/*",
            "horizonforge_school_core/static/src/calendar/*",
        ],
    },
    "installable": True,
    "application": True,
}
