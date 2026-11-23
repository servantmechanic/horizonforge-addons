from odoo import api, fields, models

ENTER_DIRECTIONS = [
    ("down", "Down to the next student"),
    ("right", "Right to the next assignment"),
]


class ResUsers(models.Model):
    _inherit = "res.users"

    school_enter_direction = fields.Selection(
        ENTER_DIRECTIONS,
        string="Gradebook: Enter Moves",
        default="down",
        required=True,
    )
    school_tab_adds_column = fields.Boolean(
        string="Gradebook: Tab Adds an Assignment",
        default=True,
        help="Tab (or Enter, moving right) past the last column, after "
        "scoring it, adds the next assignment, as in Candle.",
    )
    school_cell_letters = fields.Boolean(
        string="Gradebook: Letter in Every Cell",
        help="Show the letter beside every score in the gradebook, not only "
        "for scores typed as letters.",
    )

    @api.model_create_multi
    def create(self, vals_list):
        """New users start with the school's default."""
        for vals in vals_list:
            company = self.env["res.company"].browse(vals.get("company_id")) or self.env.company
            vals.setdefault("school_enter_direction", company.school_enter_direction)
            vals.setdefault("school_cell_letters", company.school_cell_letters)
            vals.setdefault("school_tab_adds_column", company.school_tab_adds_column)
        return super().create(vals_list)

    @property
    def SELF_READABLE_FIELDS(self):
        return super().SELF_READABLE_FIELDS + ["school_enter_direction", "school_cell_letters", "school_tab_adds_column"]

    @property
    def SELF_WRITEABLE_FIELDS(self):
        return super().SELF_WRITEABLE_FIELDS + ["school_enter_direction", "school_cell_letters", "school_tab_adds_column"]
