import random
from datetime import timedelta

from dateutil.relativedelta import relativedelta

from odoo import Command, api, fields, models

# Made-up families and vendors: the demo names no real school or business.
FAMILIES = [
    "Alder", "Birch", "Cedar", "Dogwood", "Elm", "Fir", "Hawthorn", "Juniper",
    "Larch", "Maple", "Oak", "Pine",
]
VENDORS = [
    # name, expense account xml id, monthly amount (None: occasional bills)
    ("Hillside Property Rentals", "np_account_5500", 1800.0),
    ("Valley Electric Co-op", "np_account_5600", None),
    ("Example Insurance Agency", "np_account_5700", 425.0),
    ("School Supply Depot", "np_account_5300", None),
    ("Main Street Office Supply", "np_account_5400", None),
    ("County Bookkeeping Services", "np_account_5800", 250.0),
]


class NpMove(models.Model):
    _inherit = "np.move"

    @api.model
    def _load_np_demo(self, months=4):
        """Sample books for a demo: opening balances, then ``months`` months
        up to today of tuition and other deposits, paid bills, payroll, a
        savings transfer and one unpaid bill, with the finished months'
        bank reconciliations. Does nothing when entries already exist.

        By hand: ``env["np.move"]._load_np_demo()``.
        """
        if self.search_count([], limit=1):
            return
        env = self.env
        ref = lambda xml_id: env.ref(f"nonprofit_accounting.{xml_id}")  # noqa: E731
        checking, savings = ref("np_account_1000"), ref("np_account_1010")
        rng = random.Random(26)
        today = fields.Date.context_today(self)
        start = today.replace(day=1) - relativedelta(months=months - 1)
        env.company.np_lock_date = False
        env.company.np_default_payment_account_id = checking

        Partner = env["res.partner"]
        tuition = ref("np_account_4010")
        families = Partner.create([
            {"name": f"{name} Family", "np_income_account_id": tuition.id} for name in FAMILIES
        ])
        district = ref("np_partner_district")
        vendors = Partner.create([
            {"name": name, "is_company": True, "np_expense_account_id": ref(account).id}
            for name, account, _amount in VENDORS
        ])

        def post(vals):
            move = self.create(vals)
            move.action_post()
            return move

        def items(*pairs):
            return [Command.create({"account_id": account.id, "amount": amount}) for account, amount in pairs]

        post({
            "move_type": "journal",
            "date": start - timedelta(days=1),
            "memo": "Opening balances",
            "item_line_ids": [
                Command.create({"account_id": checking.id, "debit": 18500.0}),
                Command.create({"account_id": savings.id, "debit": 42000.0}),
                Command.create({"account_id": ref("np_account_3000").id, "credit": 60500.0}),
            ],
        })
        check_number = 1201
        month = start
        while month <= today:
            def day(number):
                return min(month + timedelta(days=number - 1), today)

            # Tuition: most families pay early in the month.
            for family in families:
                if rng.random() < 0.9:
                    post({
                        "move_type": "deposit", "date": day(rng.randint(1, 10)), "bank_account_id": checking.id,
                        "partner_id": family.id, "ref": f"Check {rng.randint(1000, 9999)}",
                        "item_line_ids": items((tuition, 450.0)),
                    })
            if month.month in (8, 11, 2, 5) or month == start:
                post({
                    "move_type": "deposit", "date": day(15), "bank_account_id": checking.id,
                    "partner_id": district.id, "memo": "Quarterly district payment",
                    "item_line_ids": items((ref("np_account_4020"), 6200.0)),
                })
            post({
                "move_type": "deposit", "date": day(20), "bank_account_id": checking.id,
                "memo": "Bake sale and donations",
                "item_line_ids": items((ref("np_account_4300"), round(rng.uniform(300, 900), 2))),
            })
            # Payroll on the last day, with withholdings.
            post({
                "move_type": "payment", "date": day(28), "bill_date": day(28), "bank_account_id": checking.id,
                "memo": "Payroll", "check_number": "ACH",
                "item_line_ids": items(
                    (ref("np_account_5000"), 9600.0),
                    (ref("np_account_5100"), 734.40),
                    (ref("np_account_2100"), -1150.0),
                ),
            })
            # Bills, paid by check.
            for vendor, (name, account, amount) in zip(vendors, VENDORS):
                if amount is None:
                    amount = round(rng.uniform(80, 420), 2)
                    if rng.random() < 0.3:
                        continue
                bill_day = day(rng.randint(3, 18))
                post({
                    "move_type": "payment", "date": min(bill_day + timedelta(days=5), today),
                    "bill_date": bill_day, "bank_account_id": checking.id, "partner_id": vendor.id,
                    "ref": f"INV-{rng.randint(100, 999)}", "check_number": str(check_number),
                    "item_line_ids": items((ref(account), amount)),
                })
                check_number += 1
            post({
                "move_type": "deposit", "date": day(28), "bank_account_id": savings.id,
                "memo": "Interest", "item_line_ids": items((ref("np_account_4800"), 31.5)),
            })
            post({
                "move_type": "payment", "date": day(28), "bill_date": day(28), "bank_account_id": checking.id,
                "memo": "Monthly service fee", "item_line_ids": items((ref("np_account_6900"), 12.0)),
            })
            month += relativedelta(months=1)

        post({
            "move_type": "transfer", "date": start + timedelta(days=40), "bank_account_id": checking.id,
            "dest_account_id": savings.id, "amount": 5000.0, "memo": "To building fund savings",
        })
        # One bill still to pay, and a deposit not yet posted.
        self.create({
            "move_type": "payment", "bill_date": today - timedelta(days=3),
            "partner_id": vendors[3].id, "ref": "INV-1088",
            "item_line_ids": items((ref("np_account_5300"), 186.40)),
        })
        self.create({
            "move_type": "deposit", "date": today, "bank_account_id": checking.id,
            "partner_id": families[0].id, "item_line_ids": items((tuition, 450.0)),
        })

        # Checking reconciled for every finished month; the last few checks
        # of each month clear the bank in the next one.
        Reconciliation = env["np.reconciliation"]
        month = start
        while month + relativedelta(months=1) <= today.replace(day=1):
            end = month + relativedelta(months=1) - timedelta(days=1)
            rec = Reconciliation.create({
                "bank_account_id": checking.id, "statement_date": end, "statement_balance": 0.0,
            })
            late = rec.line_ids.filtered(lambda line: line.date > end - timedelta(days=3) and line.credit)
            (rec.line_ids - late).write({"rec_cleared": True})
            rec.statement_balance = rec.cleared_balance
            rec.action_finish()
            month += relativedelta(months=1)
