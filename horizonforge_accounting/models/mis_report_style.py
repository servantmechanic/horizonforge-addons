from odoo import api, fields, models


class MisReportStyle(models.Model):
    _inherit = "mis.report.style"

    # MIS styles have no borders. Kept out of MIS's module-level PROPS list,
    # which every database on the server shares.
    hf_rule_inherit = fields.Boolean(default=True)
    hf_rule = fields.Boolean(
        string="Rule Above",
        help="Draw a line above the row, as for totals.",
    )

    @api.model
    def merge(self, styles):
        props = super().merge(styles)
        for style in styles:
            if isinstance(style, dict):
                if "hf_rule" in style:
                    props["hf_rule"] = style["hf_rule"]
            elif style and not style.hf_rule_inherit:
                props["hf_rule"] = style.hf_rule
        return props

    @api.model
    def to_css_style(self, props, no_indent=False):
        css = super().to_css_style(props, no_indent=no_indent)
        if props.get("hf_rule"):
            css = "; ".join(filter(None, [css, "border-top: 1px solid #000"]))
        return css
