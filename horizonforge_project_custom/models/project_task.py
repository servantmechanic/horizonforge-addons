from odoo import api, fields, models

# Timesheet data a portal user must not read when the toggle is on.
PORTAL_TIME_FIELDS = frozenset({
    "allocated_hours",
    "effective_hours",
    "overtime",
    "progress",
    "remaining_hours",
    "remaining_hours_so",
    "subtask_allocated_hours",
    "subtask_effective_hours",
    "timesheet_ids",
    "total_hours_spent",
})
# Sales order data a portal user must not read when the toggle is on.
PORTAL_SALE_FIELDS = frozenset({
    "display_sale_order_button",
    "sale_line_id",
    "sale_order_id",
})
# Portal view parts that depend on the fields above, removed whole.
PORTAL_TIME_BLOCKS = (
    "//page[@name='page_timesheets']"
    " | //div[@id='allocated_hours_container']"
    " | //t[@name='allocated_hours']"
)
PORTAL_SALE_BLOCKS = (
    "//button[@name='action_project_sharing_view_so']"
    " | //span[@id='remaining_hours_so_label']"
)
PORTAL_SALE_VIEW_FIELDS = PORTAL_SALE_FIELDS | {"remaining_hours_available", "remaining_hours_so", "so_line"}


class ProjectTask(models.Model):
    _inherit = "project.task"

    hf_job_code = fields.Char(
        string="Job Code",
        related="project_id.hf_job_code",
    )
    hf_hide_from_customers = fields.Boolean(
        string="Hide from Customers",
        tracking=True,
        help="For internal work such as office time. Customers do not auto-follow "
             "this task. Customers shared with full Edit access still see every task.",
    )

    @api.model
    def _get_view_cache_key(self, view_id=None, view_type="form", **options):
        # Views drop the fields a user cannot read, so the toggles change them.
        key = super()._get_view_cache_key(view_id, view_type, **options)
        user = self.env.user
        return key + (user._hf_portal_toggle("portal_hide_timesheets"), user._hf_portal_toggle("portal_hide_sales_orders"))

    @api.model
    def _get_view(self, view_id=None, view_type="form", **options):
        # Core builds views as superuser, so unreadable fields stay in the arch
        # and the web client fails on them: remove them for portal users.
        arch, view = super()._get_view(view_id, view_type, **options)
        user = self.env.user
        if user._is_portal():
            if user._hf_portal_toggle("portal_hide_timesheets"):
                self._hf_strip_view(arch, PORTAL_TIME_BLOCKS, PORTAL_TIME_FIELDS)
            if user._hf_portal_toggle("portal_hide_sales_orders"):
                self._hf_strip_view(arch, PORTAL_SALE_BLOCKS, PORTAL_SALE_VIEW_FIELDS)
        return arch, view

    @api.model
    def _hf_strip_view(self, arch, blocks, field_names):
        for node in arch.xpath(blocks):
            node.getparent().remove(node)
        for node in arch.xpath("//field | //label"):
            if (node.get("name") or node.get("for")) in field_names:
                node.getparent().remove(node)

    def _has_field_access(self, field, operation):
        if (
            operation == "read"
            and not self.env.su
            and field.name in PORTAL_TIME_FIELDS | PORTAL_SALE_FIELDS
            and self.env.user._is_portal()
        ):
            toggle = "portal_hide_timesheets" if field.name in PORTAL_TIME_FIELDS else "portal_hide_sales_orders"
            if self.env.user._hf_portal_toggle(toggle):
                return False
        return super()._has_field_access(field, operation)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            parent = self.browse(vals.get("parent_id")).sudo()
            if parent.hf_hide_from_customers:
                vals["hf_hide_from_customers"] = True
        # Core subscribes some project followers while creating the task: mark
        # them too, or unfollowing the project would treat them as hand-added.
        auto_follow = self.env.user._hf_portal_toggle("auto_follow_tasks")
        tasks = super(ProjectTask, self.with_context(hf_auto_follow=auto_follow)).create(vals_list)
        tasks = tasks.with_env(self.env)
        if auto_follow:
            tasks.project_id._hf_auto_follow_tasks(tasks=tasks)
        self.env["mail.followers"].sudo().search([
            ("res_model", "=", "project.task"),
            ("res_id", "in", tasks.filtered("hf_hide_from_customers").ids),
            ("partner_id.partner_share", "=", True),
        ]).unlink()
        return tasks

    def write(self, vals):
        res = super().write(vals)
        if "stage_id" in vals and self.env["project.task.type"].browse(vals["stage_id"]).sudo().hf_closes_task:
            self.sudo().filtered(lambda t: not t.is_closed).state = "1_done"
        if "project_id" in vals or "hf_hide_from_customers" in vals:
            self._hf_sync_auto_follows()
        if vals.get("hf_hide_from_customers"):
            subtasks = self._get_all_subtasks()
            if subtasks:
                subtasks.hf_hide_from_customers = True
        return res

    def _hf_sync_auto_follows(self):
        """Replace auto-added followers after a move or a change of the hide box."""
        self.env["mail.followers"].sudo().search([
            ("res_model", "=", "project.task"),
            ("res_id", "in", self.ids),
            ("hf_auto_followed", "=", True),
        ]).unlink()
        if self.env.user._hf_portal_toggle("auto_follow_tasks"):
            self.project_id._hf_auto_follow_tasks(tasks=self)

    def _message_subscribe(self, partner_ids=None, subtype_ids=None, customer_ids=None):
        tasks = self
        if self.env.context.get("hf_skip_hidden_tasks"):
            tasks = self.filtered(lambda t: not t.hf_hide_from_customers)
        return super(ProjectTask, tasks)._message_subscribe(partner_ids, subtype_ids, customer_ids)

    def message_unsubscribe(self, partner_ids=None):
        if self.env.context.get("hf_keep_customer_tasks") and partner_ids:
            partners = self.env["res.partner"].sudo().browse(partner_ids)
            partner_ids = partners.filtered(lambda p: not p.partner_share).ids
        return super().message_unsubscribe(partner_ids=partner_ids)
