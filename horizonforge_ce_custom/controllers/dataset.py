from odoo import _, http
from odoo.exceptions import ValidationError
from odoo.http import request

from odoo.addons.web.controllers import dataset


class DataSet(dataset.DataSet):

    @http.route()
    def call_kw(self, model, method, args, kwargs, path=None):
        # Only the web client's name_create RPC (typing a new name in a
        # many2one and pressing Tab/Enter) is blocked. Server-side callers,
        # such as mail creating a contact from an incoming email, are not.
        # A ValidationError makes the web client open the full Create form.
        if method == "name_create" and request.env.user._hf_quick_create_blocked(model):
            raise ValidationError(_(
                "Quick-create is turned off for %s. Use \"Create and edit...\" "
                "to fill in the full form.",
                request.env[model]._description,
            ))
        return super().call_kw(model, method, args, kwargs, path=path)
