{
    "name": "HorizonForge Project Customizations",
    "version": "19.0.1.2.0",
    "category": "Services/Project",
    "summary": "Job tracking for small contractors: portal privacy toggles, "
               "auto-follow of tasks, timesheet payroll report, job setup defaults",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Job tracking for small contractors. See README.md.",
    "author": "Ozark AG LLC",
    "license": "LGPL-3",
    "depends": ["project", "hr_timesheet", "sale_project", "sale_timesheet", "portal", "account"],
    "external_dependencies": {"python": ["xlsxwriter"]},
    "data": [
        "security/ir.model.access.csv",
        "security/portal_rules.xml",
        "security/res_groups.xml",
        "data/project_defaults.xml",
        "views/res_config_settings_views.xml",
        "views/project_task_views.xml",
        "views/project_project_views.xml",
        "views/sale_order_views.xml",
        "views/account_move_views.xml",
        "report/timesheet_payroll_report.xml",
        "report/timesheet_payroll_templates.xml",
        "wizard/timesheet_payroll_wizard_views.xml",
    ],
    "post_init_hook": "_hf_project_post_init",
    "installable": True,
}
