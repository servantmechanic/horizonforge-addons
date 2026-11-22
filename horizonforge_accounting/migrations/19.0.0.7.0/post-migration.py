from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # account_in_payment came in with this version. Invoices and bills paid
    # by a payment the bank hasn't cleared were stored as Paid; recompute them
    # so they show In Payment until reconciled.
    env = api.Environment(cr, SUPERUSER_ID, {})
    moves = env["account.move"].search([
        ("payment_state", "=", "paid"),
        ("move_type", "in", env["account.move"].get_invoice_types(include_receipts=True)),
    ])
    env.add_to_compute(moves._fields["payment_state"], moves)
    moves._recompute_recordset(["payment_state"])
