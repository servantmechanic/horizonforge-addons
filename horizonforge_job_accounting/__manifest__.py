{
    "name": "HorizonForge Job Accounting",
    "version": "19.0.0.1.0",
    "category": "Accounting",
    "summary": "Job profitability for HorizonForge jobs: revenue, labor, bills and "
               "margin per job, with drill-down to every line",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Job profitability reports. See README.md.",
    "author": "Ozark AG LLC",
    "license": "AGPL-3",
    "depends": ["horizonforge_project_custom", "horizonforge_accounting"],
    "data": [
        "security/ir.model.access.csv",
        "security/hf_job_profit_security.xml",
        "views/hf_job_profit_line_views.xml",
        "views/project_project_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "auto_install": True,
    "installable": True,
}
