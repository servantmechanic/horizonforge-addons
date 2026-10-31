from odoo import http
from odoo.http import request

from odoo.addons.hr_timesheet.controllers.portal import TimesheetProjectCustomerPortal
from odoo.addons.sale.controllers.portal import CustomerPortal
from odoo.addons.sale_project.controllers.portal import SaleProjectCustomerPortal
from odoo.addons.sale_timesheet.controllers.portal import SaleTimesheetCustomerPortal


class HfSaleCustomerPortal(CustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if request.env.user._hf_portal_toggle("portal_hide_sales_orders"):
            # A zero count keeps the tile hidden on the portal home page.
            for counter in ("quotation_count", "order_count"):
                if counter in values:
                    values[counter] = 0
        return values

    @http.route()
    def portal_my_quotes(self, **kwargs):
        if request.env.user._hf_portal_toggle("portal_hide_sales_orders"):
            return request.redirect("/my")
        return super().portal_my_quotes(**kwargs)

    @http.route()
    def portal_my_orders(self, **kwargs):
        if request.env.user._hf_portal_toggle("portal_hide_sales_orders"):
            return request.redirect("/my")
        return super().portal_my_orders(**kwargs)


class HfTimesheetCustomerPortal(SaleTimesheetCustomerPortal):

    def _prepare_home_portal_values(self, counters):
        values = super()._prepare_home_portal_values(counters)
        if "timesheet_count" in values and request.env.user._hf_portal_toggle("portal_hide_timesheets"):
            values["timesheet_count"] = 0
        return values

    @http.route()
    def portal_my_timesheets(self, *args, **kw):
        if request.env.user._hf_portal_toggle("portal_hide_timesheets"):
            return request.redirect("/my")
        return super().portal_my_timesheets(*args, **kw)


class HfProjectCustomerPortal(SaleProjectCustomerPortal, TimesheetProjectCustomerPortal):

    def _task_get_searchbar_groupby(self, milestones_allowed, project=False):
        values = super()._task_get_searchbar_groupby(milestones_allowed, project)
        if request.env.user._hf_portal_toggle("portal_hide_sales_orders"):
            values.pop("sale_line_id", None)
        return values

    def _task_get_searchbar_inputs(self, milestones_allowed, project=False):
        values = super()._task_get_searchbar_inputs(milestones_allowed, project)
        if request.env.user._hf_portal_toggle("portal_hide_sales_orders"):
            values.pop("sale_order", None)
        return values

    def _show_task_report(self, task_sudo, report_type, download):
        # The task report is a timesheet printout, reachable by URL.
        if request.env.user._hf_portal_toggle("portal_hide_timesheets"):
            return request.redirect("/my")
        return super()._show_task_report(task_sudo, report_type, download)
