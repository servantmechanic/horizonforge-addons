from odoo import api, fields, models


class ProjectProject(models.Model):
    _inherit = "project.project"
    _rec_names_search = ["name", "hf_job_code"]

    hf_job_code = fields.Char(
        string="Job Code",
        related="account_id.code",
        store=True,
        readonly=False,
        help="Numbered automatically and kept as the code of the job's analytic "
             "account, so its time, invoices and bills can all be found by it.",
    )

    @api.depends_context("hf_show_job_code")
    def _compute_display_name(self):
        super()._compute_display_name()
        if self.env.context.get("hf_show_job_code"):
            for project in self.filtered("hf_job_code"):
                project.display_name = f"[{project.hf_job_code}] {project.display_name}"

    def _hf_assign_job_codes(self):
        """Number jobs whose analytic account has no code yet."""
        projects = self.sudo().filtered(lambda p: not p.is_template and not p.is_internal_project)
        for account in projects.account_id.filtered(lambda a: not a.code):
            account.code = self.env["ir.sequence"].sudo().next_by_code("horizonforge_project_custom.job_code")

    @api.model_create_multi
    def create(self, vals_list):
        projects = super().create(vals_list)
        projects._hf_assign_job_codes()
        return projects

    def write(self, vals):
        res = super().write(vals)
        if "account_id" in vals or "allow_timesheets" in vals:
            self._hf_assign_job_codes()
        return res

    def _hf_task_subtypes(self, project_subtypes):
        """Map a project follower's subtypes to task ones, as core does."""
        return project_subtypes.parent_id | project_subtypes.filtered(lambda sub: sub.internal or sub.default)

    def _hf_auto_follow_tasks(self, tasks=None, partners=None):
        """Subscribe this project's customer followers to its tasks.

        :param tasks: limit to these tasks, all of the project's when empty
        :param partners: limit to these partners, all followers when empty
        """
        followers_model = self.env["mail.followers"].sudo().with_context(hf_auto_follow=True)
        for project in self.sudo():
            project_tasks = tasks.filtered(lambda t: t.project_id == project) if tasks else project.tasks
            task_ids = project_tasks.filtered(lambda t: not t.hf_hide_from_customers and not t.is_template).ids
            followers = project.message_follower_ids.filtered(
                lambda f: f.partner_id.partner_share and (not partners or f.partner_id in partners)
            )
            if not task_ids or not followers:
                continue
            default_subtype = self.env.ref("mail.mt_comment")
            subtypes = {
                follower.partner_id.id: (self._hf_task_subtypes(follower.subtype_ids) or default_subtype).ids
                for follower in followers
            }
            followers_model._insert_followers(
                "project.task", task_ids, list(subtypes), subtypes=subtypes, existing_policy="skip",
            )

    def action_hf_backfill_task_followers(self):
        """Apply auto-follow to followers that predate it."""
        self._hf_auto_follow_tasks()

    def _message_subscribe(self, partner_ids=None, subtype_ids=None, customer_ids=None):
        res = super()._message_subscribe(partner_ids, subtype_ids, customer_ids)
        if partner_ids and self.env.user._hf_portal_toggle("auto_follow_tasks"):
            self._hf_auto_follow_tasks(partners=self.env["res.partner"].browse(partner_ids))
        return res

    def _add_followers(self, partners):
        # Core also subscribes partners to the tasks they are the customer of.
        return super(ProjectProject, self.with_context(hf_skip_hidden_tasks=True))._add_followers(partners)

    def message_unsubscribe(self, partner_ids=None):
        if not self.env.user._hf_portal_toggle("auto_follow_tasks"):
            return super().message_unsubscribe(partner_ids=partner_ids)
        # Core unsubscribes the partners from every open task; keep hand-added
        # customer follows and remove only what auto-follow added.
        res = super(ProjectProject, self.with_context(hf_keep_customer_tasks=True)).message_unsubscribe(
            partner_ids=partner_ids,
        )
        if partner_ids:
            self.env["mail.followers"].sudo().search([
                ("res_model", "=", "project.task"),
                ("res_id", "in", self.sudo().with_context(active_test=False).tasks.ids),
                ("partner_id", "in", partner_ids),
                ("hf_auto_followed", "=", True),
            ]).unlink()
        return res
