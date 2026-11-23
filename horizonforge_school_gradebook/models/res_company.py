from odoo import api, fields, models

from .res_users import ENTER_DIRECTIONS
from .school_assignment import ENTRY_MODES

CARD_LETTER = (
    "This report is to inform you of your child's performance in their "
    "studies and conduct at school. Please read it carefully and discuss it "
    "with your child.\n\n"
    "The school requests your support so that your child does their best at "
    "school. We invite you to visit school and observe your child at work. "
    "We also encourage you to discuss your child's progress with their teacher."
)

CONDUCT_TRAITS = """Classroom Behaviour
- Avoids disturbing others
- Has good posture
- Pays attention in class
- Speaks with good volume and enunciation
Interpersonal Relationships
- Is mannerly
- Is thoughtful and gracious
- Respects others' feelings
- Respects others' property
- Works and plays well with others
Spiritual & Moral Traits
- Accepts direction cheerfully
- Is honest & trustworthy
- Is respectful
- Obeys school rules
- Shows interest in spiritual matters
- Shows self-control
- Uses wholesome speech
Stewardship
- Cares for school property
- Keeps desk and books tidy
Work Habits
- Enjoys study
- Follows directions
- Shows effort and perseverance
- Stays current with assignments
- Uses time well
- Works carefully"""


class ResCompany(models.Model):
    _inherit = "res.company"

    school_enter_direction = fields.Selection(
        ENTER_DIRECTIONS,
        string="Gradebook: Enter Moves",
        default="down",
        required=True,
        help="The default for new users. Each teacher can change their own "
        "in My Preferences, or in the gradebook's top bar.",
    )
    school_cell_letters = fields.Boolean(
        string="Gradebook: Letter in Every Cell",
        help="The default for new users. Each teacher can change their own "
        "in My Preferences, or in the gradebook's top bar.",
    )
    school_entry_mode = fields.Selection(
        ENTRY_MODES,
        string="Entry Mode",
        default="percent",
        required=True,
        help="What teachers type in the gradebook, unless a class or an "
        "assignment says otherwise.",
    )
    school_missing_work = fields.Selection(
        [
            ("zero", "Counts as 0"),
            ("skip", "Left out until entered"),
        ],
        string="Missing Work",
        default="zero",
        required=True,
        help="How a score marked missing (M) counts in the averages. "
        "Excused scores and empty cells never count.",
    )
    school_grade_decimals = fields.Integer(
        string="Grade Decimals",
        default=0,
        help="Decimals of the period and year grades. 0 rounds to a whole "
        "number, half up: 92.5 becomes 93. The letter is looked up on the "
        "rounded grade.",
    )
    school_display_decimals = fields.Integer(
        string="Average Decimals",
        default=1,
        help="Decimals shown for category and class averages.",
    )
    school_year_grade = fields.Selection(
        [
            ("average", "Average of the period grades"),
            ("cumulative", "Cumulative over all the year's scores"),
        ],
        string="Year Grade",
        default="average",
        required=True,
    )
    school_weight_scheme_id = fields.Many2one(
        "school.weight.scheme",
        string="Weight Scheme",
        help="Used by every course and class without its own weight scheme.",
    )
    school_grading_scale_id = fields.Many2one(
        "school.grading.scale",
        string="Grading Scale",
        help="Used by every grade level and course without its own scale.",
    )

    school_card_motto = fields.Text(
        string="Report Card Motto",
        help="A verse or motto printed on the report card cover. Leave empty for none.",
    )
    school_card_letter = fields.Text(
        string="Letter to Parents",
        default=CARD_LETTER,
        help="Printed on the report card cover. Leave empty for none.",
    )
    school_card_letter_signature = fields.Char(
        string="Letter Signed By",
        default="The School Board and Teachers",
    )
    school_conduct_traits = fields.Text(
        string="Conduct Traits",
        default=CONDUCT_TRAITS,
        help="The conduct grades on the report card, printed with empty boxes "
        "for the teacher to fill in. One per line: a heading, then its traits "
        "starting with a dash. Leave empty to print no conduct grades.",
    )

    _school_decimals_range = models.Constraint(
        "CHECK(school_grade_decimals BETWEEN 0 AND 2 AND school_display_decimals BETWEEN 0 AND 2)",
        "Grade and average decimals must be between 0 and 2.",
    )

    def _school_conduct_lines(self):
        """The conduct traits as ``[(is_heading, text)]``."""
        self.ensure_one()
        lines = []
        for line in (self.school_conduct_traits or "").splitlines():
            text = line.strip()
            if not text:
                continue
            if text[0] in "-*•":
                lines.append((False, text[1:].strip()))
            else:
                lines.append((True, text))
        return lines

    @api.model
    def _school_gradebook_set_defaults(self):
        """Give companies without them the shipped weight scheme and scale."""
        scheme = self.env.ref(
            "horizonforge_school_gradebook.weight_scheme_standard", raise_if_not_found=False
        )
        scale = self.env.ref(
            "horizonforge_school_gradebook.grading_scale_letters", raise_if_not_found=False
        )
        for company in self.search([]):
            if scheme and not company.school_weight_scheme_id:
                company.school_weight_scheme_id = scheme
            if scale and not company.school_grading_scale_id:
                company.school_grading_scale_id = scale
