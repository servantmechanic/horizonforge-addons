from odoo import _, api, models
from odoo.fields import Domain
from odoo.tools import escape_psql


class ResPartner(models.Model):
    _inherit = "res.partner"

    @api.onchange("name", "email", "phone")
    def _onchange_hf_duplicate_warning(self):
        """Warn (without blocking) when another contact has the same name,
        email or phone."""
        domains = []
        if self.name and self.name.strip():
            domains.append(Domain("name", "=ilike", escape_psql(self.name.strip())))
        if self.email and self.email.strip():
            domains.append(Domain("email", "=ilike", escape_psql(self.email.strip())))
        if self.phone and self.phone.strip():
            domains.append(Domain("phone", "=", self.phone.strip()))
        if not domains:
            return None
        domain = Domain.OR(domains)
        if self._origin.id:
            domain &= Domain("id", "!=", self._origin.id)
        # A company's own contacts often share its phone and email.
        if self.parent_id:
            domain &= Domain("commercial_partner_id", "!=", self.parent_id.commercial_partner_id.id)
        matches = self.search(domain, limit=3)
        if not matches:
            return None
        return {"warning": {
            "title": _("Possible duplicate contact"),
            "message": _(
                "A contact with the same name, email or phone already exists: %s",
                ", ".join(matches.mapped("display_name")),
            ),
        }}
