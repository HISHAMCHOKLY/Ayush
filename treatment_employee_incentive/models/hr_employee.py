from odoo import fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    treatment_incentive_history_ids = fields.One2many(
        "treatment.incentive.history",
        "employee_id",
        string="Treatment History",
        readonly=True,
    )
    treatment_incentive_history_count = fields.Integer(
        string="Treatment History Count",
        compute="_compute_treatment_incentive_history_count",
    )

    def _compute_treatment_incentive_history_count(self):
        History = self.env["treatment.incentive.history"]
        for employee in self:
            employee.treatment_incentive_history_count = History.search_count([
                ("employee_id", "=", employee.id)
            ])
