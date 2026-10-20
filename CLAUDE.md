# custom-addons

Custom Odoo 19 **Community** addons. This folder is on Odoo's `addons_path`.

## Environment

- Odoo source: `~/odoo-dev/odoo` (Odoo 19, Python 3.11 venv at `~/odoo-dev/venv`)
- Config: `~/odoo-dev/odoo.conf`, dev database `dev19`, http://localhost:8069
- OCA addons: `~/odoo-dev/oca/web` (OCA/web, branch 19.0, on `addons_path`).
  `web_responsive` is installed in `dev19` for the app launcher. Update with
  `git -C ~/odoo-dev/oca/web pull`, then `-u web_responsive`.
- Odoo Enterprise is **not** available. Never depend on Enterprise modules
  (`account_accountant`, `account_reports`, etc.).

## Commands

Run from `~/odoo-dev`:

```bash
# Start the server
venv/bin/python odoo/odoo-bin -c odoo.conf

# Install / upgrade a module in the dev database
venv/bin/python odoo/odoo-bin -c odoo.conf -d dev19 -u <module> --stop-after-init

# Run a module's tests in a throwaway database (never run tests against dev19)
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_<module> -i <module> \
    --test-tags /<module> --stop-after-init
```

- If the dev server is already running on 8069, add `--http-port 8079` to test runs.
- Browser (HttpCase) tests need Chrome and the `websocket-client` package in the venv
  (`uv pip install --python venv/bin/python websocket-client`); without it they are skipped.

## Modules

| Module | Status | Notes |
|---|---|---|
| `ozark_timecard` | In production (v2.1) | Don't change it unless asked |
| `nonprofit_accounting` | In development | Standalone cash-basis ledger (small school). See its `PLAN.md` |
| `horizonforge_ce_custom` | In development | Generic CE tweaks (home action, no quick-create, debranding). Install on every database |

## Odoo 19 conventions

- Use `models.Constraint(...)` / `models.Index(...)` class attributes, not `_sql_constraints`.
- Views: use `<list>`, not `<tree>`. Use `invisible="..."` / `readonly="..."` expressions, not `attrs`.
- Security groups use `res.groups.privilege` (not the old `category_id` pattern).
- Manifest version format is `19.0.MAJOR.MINOR.PATCH`.
- Every new model gets a line in `security/ir.model.access.csv` and tests in `tests/`.
- Match the existing style: double quotes, `fields.X(string=..., help=...)` on separate lines.

## Workflow

- `main` is the stable branch. Do work on a `feature/<name>` branch.
- Before committing, install/upgrade the module and run its tests.
- Keep commits small, with a clear message about what changed and why.
