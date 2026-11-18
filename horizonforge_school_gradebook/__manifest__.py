{
    "name": "School Gradebook",
    "version": "19.0.0.7.0",
    "category": "School",
    "summary": "Keyboard-driven gradebook for small schools: score categories, "
               "weights, grading scales, assignment schedules and a spreadsheet-style grid",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Gradebook for the school addons. See README.md.",
    "author": "Ozark AG LLC",
    "license": "LGPL-3",
    "depends": ["horizonforge_school_core", "web"],
    "data": [
        "security/school_gradebook_security.xml",
        "security/ir.model.access.csv",
        "data/school_gradebook_data.xml",
        "views/school_score_category_views.xml",
        "views/school_weight_scheme_views.xml",
        "views/school_grading_scale_views.xml",
        "views/school_assignment_template_views.xml",
        "views/school_assignment_views.xml",
        "views/school_period_mark_views.xml",
        "views/school_core_views.xml",
        "views/res_config_settings_views.xml",
        "wizard/school_assignment_generate_views.xml",
        "wizard/school_grade_report_views.xml",
        "wizard/school_setup_guide_views.xml",
        "report/school_grade_reports.xml",
        "report/school_grade_report_templates.xml",
        "views/menus.xml",
    ],
    "demo": [
        "demo/school_gradebook_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "horizonforge_school_gradebook/static/src/gradebook/*",
        ],
    },
    "installable": True,
}
