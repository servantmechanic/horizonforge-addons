{
    "name": "HorizonForge Accounting",
    "version": "19.0.0.3.0",
    "category": "Accounting",
    "summary": "Small-business books on Community: OCA reports, reconciliation and "
               "bank feeds, contractor starter accounts and journals",
    # Set, or Odoo parses README.md as reStructuredText and logs errors.
    "description": "Small-business accounting for Odoo Community. See README.md.",
    "author": "Ozark AG LLC",
    "license": "AGPL-3",
    "depends": [
        "account",
        "account_check_printing",
        "l10n_us",
        "horizonforge_ce_custom",
        # OCA/account-financial-tools
        "account_usability",
        "account_fiscal_year",
        "account_lock_date_update",
        "account_asset_management",
        "account_move_template",
        # OCA/account-financial-reporting and OCA/mis-builder
        "account_financial_report",
        "partner_statement",
        "mis_builder",
        "mis_builder_budget",
        "mis_builder_cash_flow",
        # OCA/account-reconcile and OCA/bank-statement-import
        "account_reconcile_oca",
        "account_statement_import_online",
        "account_statement_import_sheet_file_xlsx",
        "account_statement_import_file_reconcile_oca",
        "account_statement_import_online_plaid",
    ],
    "data": [
        "data/statement_import_maps.xml",
        "views/account_journal_dashboard_views.xml",
    ],
    "post_init_hook": "_hf_accounting_post_init",
    "installable": True,
}
