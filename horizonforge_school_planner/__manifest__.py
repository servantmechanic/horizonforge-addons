{
    "name": "School Planner",
    "version": "19.0.0.8.0",
    "category": "School",
    "summary": "Pacing guides per course, laid over the school calendar: "
               "progress, plans that move with the class, weekly plans",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Lesson planning for the school addons. See README.md.",
    "author": "Ozark AG LLC",
    "license": "LGPL-3",
    "depends": ["horizonforge_school_gradebook"],
    "data": [
        "security/school_planner_security.xml",
        "security/ir.model.access.csv",
        "views/school_pacing_item_views.xml",
        "views/school_pacing_guide_views.xml",
        "views/school_plan_line_views.xml",
        "views/school_core_views.xml",
        "wizard/school_pacing_transfer_views.xml",
        "wizard/school_weekly_plan_views.xml",
        "report/school_weekly_plan_report.xml",
        "views/menus.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "horizonforge_school_planner/static/src/planner/*",
        ],
    },
    "demo": [
        "demo/school_planner_demo.xml",
    ],
    "uninstall_hook": "uninstall_hook",
    "installable": True,
}
