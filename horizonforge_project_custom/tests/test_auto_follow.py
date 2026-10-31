from odoo.tests import TransactionCase, new_test_user, tagged


@tagged("post_install", "-at_install")
class TestAutoFollow(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.customer = cls.env["res.partner"].create({"name": "Customer"})
        cls.staff = new_test_user(cls.env, login="hf_staff", groups="project.group_project_manager")
        cls.project = cls.env["project.project"].create({
            "name": "Job",
            "privacy_visibility": "portal",
        })
        cls.task_a = cls.env["project.task"].create({"name": "A", "project_id": cls.project.id})
        cls.task_b = cls.env["project.task"].create({"name": "B", "project_id": cls.project.id})

    def _param(self, name, value):
        self.env["ir.config_parameter"].sudo().set_param(f"horizonforge_project_custom.{name}", value)

    def _follower(self, task, partner=None):
        return task.message_follower_ids.filtered(lambda f: f.partner_id == (partner or self.customer))

    def test_follow_covers_existing_and_new_tasks(self):
        self.project.message_subscribe([self.customer.id])
        self.assertIn(self.customer, self.task_a.message_partner_ids)
        self.assertIn(self.customer, self.task_b.message_partner_ids)
        new_task = self.env["project.task"].create({"name": "C", "project_id": self.project.id})
        self.assertIn(self.customer, new_task.message_partner_ids)

    def test_closed_tasks_are_covered(self):
        self.task_a.state = "1_done"
        self.project.message_subscribe([self.customer.id])
        self.assertIn(self.customer, self.task_a.message_partner_ids)

    def test_subtypes_are_task_subtypes(self):
        project_subtype = self.env.ref("project.mt_project_task_new")
        self.project.message_subscribe([self.customer.id], subtype_ids=project_subtype.ids)
        subtypes = self._follower(self.task_a).subtype_ids
        self.assertIn(self.env.ref("project.mt_task_new"), subtypes)
        self.assertNotIn(project_subtype, subtypes)

    def test_internal_followers_are_skipped(self):
        self.project.message_subscribe([self.staff.partner_id.id])
        self.assertNotIn(self.staff.partner_id, self.task_a.message_partner_ids)

    def test_toggle_off(self):
        self._param("auto_follow_tasks", False)
        self.project.message_subscribe([self.customer.id])
        self.assertNotIn(self.customer, self.task_a.message_partner_ids)

    def test_unfollow_removes_tasks_created_after_follow(self):
        self.project.message_subscribe([self.customer.id])
        new_task = self.env["project.task"].create({"name": "C", "project_id": self.project.id})
        self.assertTrue(self._follower(new_task).hf_auto_followed)
        self.project.message_unsubscribe([self.customer.id])
        self.assertNotIn(self.customer, new_task.message_partner_ids)

    def test_new_hidden_task_is_skipped(self):
        self.project.message_subscribe([self.customer.id])
        task = self.env["project.task"].create({
            "name": "Office time", "project_id": self.project.id, "hf_hide_from_customers": True,
        })
        self.assertNotIn(self.customer, task.message_partner_ids)

    def test_unfollow_keeps_hand_added(self):
        self.task_a.message_subscribe([self.customer.id])
        self.project.message_subscribe([self.customer.id])
        self.assertFalse(self._follower(self.task_a).hf_auto_followed)
        self.assertTrue(self._follower(self.task_b).hf_auto_followed)
        self.project.message_unsubscribe([self.customer.id])
        self.assertIn(self.customer, self.task_a.message_partner_ids)
        self.assertNotIn(self.customer, self.task_b.message_partner_ids)

    def test_unfollow_removes_closed_tasks(self):
        self.project.message_subscribe([self.customer.id])
        self.task_b.state = "1_done"
        self.project.message_unsubscribe([self.customer.id])
        self.assertNotIn(self.customer, self.task_b.message_partner_ids)

    def test_unfollow_still_removes_internal_followers(self):
        self.task_a.message_subscribe([self.staff.partner_id.id])
        self.project.message_unsubscribe([self.staff.partner_id.id])
        self.assertNotIn(self.staff.partner_id, self.task_a.message_partner_ids)

    def test_hidden_task_is_skipped(self):
        self.task_a.hf_hide_from_customers = True
        self.project.message_subscribe([self.customer.id])
        self.assertNotIn(self.customer, self.task_a.message_partner_ids)
        self.assertIn(self.customer, self.task_b.message_partner_ids)

    def test_hiding_removes_auto_follows_only(self):
        self.task_a.message_subscribe([self.customer.id])
        self.project.message_subscribe([self.customer.id])
        (self.task_a | self.task_b).hf_hide_from_customers = True
        self.assertIn(self.customer, self.task_a.message_partner_ids)
        self.assertNotIn(self.customer, self.task_b.message_partner_ids)
        self.task_b.hf_hide_from_customers = False
        self.assertIn(self.customer, self.task_b.message_partner_ids)

    def test_hidden_task_with_customer_set(self):
        """Core subscribes the task's customer when sharing; hidden tasks stay out."""
        self.task_a.write({"partner_id": self.customer.id, "hf_hide_from_customers": True})
        self.task_b.partner_id = self.customer
        self.project._add_followers(self.customer)
        self.assertNotIn(self.customer, self.task_a.message_partner_ids)
        self.assertIn(self.customer, self.task_b.message_partner_ids)

    def test_subtasks_inherit_hidden(self):
        child = self.env["project.task"].create({
            "name": "Child", "project_id": self.project.id, "parent_id": self.task_a.id,
        })
        self.project.message_subscribe([self.customer.id])
        self.assertIn(self.customer, child.message_partner_ids)
        self.task_a.hf_hide_from_customers = True
        self.assertTrue(child.hf_hide_from_customers)
        self.assertNotIn(self.customer, child.message_partner_ids)
        grandchild = self.env["project.task"].create({
            "name": "Grandchild", "project_id": self.project.id, "parent_id": child.id,
        })
        self.assertTrue(grandchild.hf_hide_from_customers)
        self.assertNotIn(self.customer, grandchild.message_partner_ids)

    def test_hiding_with_other_values_leaves_subtask_stage(self):
        stages = self.env["project.task.type"].create([
            {"name": "One", "project_ids": [(4, self.project.id)]},
            {"name": "Two", "project_ids": [(4, self.project.id)]},
        ])
        child = self.env["project.task"].create({
            "name": "Child", "project_id": self.project.id, "parent_id": self.task_a.id, "stage_id": stages[0].id,
        })
        self.task_a.write({"hf_hide_from_customers": True, "stage_id": stages[1].id})
        self.assertTrue(child.hf_hide_from_customers)
        self.assertEqual(child.stage_id, stages[0])

    def test_new_hidden_task_is_skipped_with_toggle_off(self):
        self.project.message_subscribe([self.customer.id])
        self._param("auto_follow_tasks", False)
        task = self.env["project.task"].create({
            "name": "Office time", "project_id": self.project.id, "hf_hide_from_customers": True,
        })
        self.assertNotIn(self.customer, task.message_partner_ids)

    def test_moved_task_follows_new_project(self):
        other = self.env["project.project"].create({"name": "Other", "privacy_visibility": "portal"})
        other_customer = self.env["res.partner"].create({"name": "Other Customer"})
        other.message_subscribe([other_customer.id])
        self.project.message_subscribe([self.customer.id])
        self.task_a.project_id = other
        self.assertNotIn(self.customer, self.task_a.message_partner_ids)
        self.assertIn(other_customer, self.task_a.message_partner_ids)

    def test_backfill(self):
        self._param("auto_follow_tasks", False)
        self.project.message_subscribe([self.customer.id])
        self.task_b.hf_hide_from_customers = True
        self.project.action_hf_backfill_task_followers()
        self.assertIn(self.customer, self.task_a.message_partner_ids)
        self.assertTrue(self._follower(self.task_a).hf_auto_followed)
        self.assertNotIn(self.customer, self.task_b.message_partner_ids)
