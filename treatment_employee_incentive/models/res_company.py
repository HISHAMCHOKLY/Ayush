from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    treatment_incentive_percentage = fields.Float(
        string="Treatment Incentive Percentage",
        default=5.0,
        help="Percentage of the actual paid treatment value allocated to each therapist."
    )
    treatment_incentive_monthly_target = fields.Monetary(
        string="Monthly Incentive Amount Target",
        currency_field="currency_id",
        default=50000.0,
        help="Monthly target for the employee's accumulated percentage-based incentive amount, excluding any target-achievement bonus. After reaching it, a new target cycle begins."
    )
    treatment_incentive_target_bonus_amount = fields.Monetary(
        string="Bonus for Achieving Target",
        currency_field="currency_id",
        default=0.0,
        help="Extra bonus paid to a therapist when their accumulated percentage-based incentive reaches the configured incentive target in a cycle. Keep zero until the bonus value is decided."
    )
