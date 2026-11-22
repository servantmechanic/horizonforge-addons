# HorizonForge CE Customizations

Small, safe usability tweaks for any Odoo 19 Community database. It changes
behavior only (no new data models) and is meant to be installed everywhere.

| Tweak | What it does |
|---|---|
| No quick-create | Typing a new name in a contact or product field opens the full Create form instead of creating a bare record. On by default; Settings, Data Entry |
| Duplicate contact warning | A new contact with the same name, email or phone as another one shows a warning (it doesn't block) |
| + and - on dates | On any editable date or date-and-time field, `+` (or `=`) and `-` move the date a day later or earlier, from today when empty. While a date is being typed, the keys are typed as usual |
| Home action | The user form and preferences show **Home Action**, so each user can choose the screen they land on |
| Simple interface | Optional (Settings, Interface): users who are not administrators don't see Discuss, Contacts, Apps, the chat and activity icons or OdooBot |
| One-app users | No app switcher for a user with a single app |
| No odoo.com links | Help and My Odoo.com Account are removed from the user menu; the daily usage report to odoo.com isn't sent |
| No public sign-up | Accounts are by invitation only: free sign-up on the login page is turned off at install |
| Chat above the launcher | With OCA `web_responsive`, a chat window opened over the app launcher stays visible |

## Install

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d <database> -i horizonforge_ce_custom --stop-after-init
```

## Tests

```bash
venv/bin/python odoo/odoo-bin -c odoo.conf -d test_horizonforge_ce_custom \
    -i horizonforge_ce_custom --test-tags /horizonforge_ce_custom --stop-after-init
```

Browser tests need Chrome and the `websocket-client` package.
