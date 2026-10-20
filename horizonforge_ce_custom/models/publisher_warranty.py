import logging

from odoo import models

_logger = logging.getLogger(__name__)


class PublisherWarrantyContract(models.AbstractModel):
    _inherit = "publisher_warranty.contract"

    def update_notification(self, cron_mode=True):
        """Don't send the daily usage report to odoo.com (Community has no
        subscription to check)."""
        _logger.info("odoo.com update notification disabled by horizonforge_ce_custom")
        return True
