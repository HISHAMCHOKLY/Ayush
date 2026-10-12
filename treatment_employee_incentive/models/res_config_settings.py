from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    company_currency_id = fields.Many2one(
        "res.currency",
        related="company_id.currency_id",
        readonly=True,
    )

    # These settings are editable on res.config.settings and persist in
    # regular res.company fields, not in ir.config_parameter key-value rows.
    treatment_incentive_percentage = fields.Float(
        string="Treatment Incentive Percentage",
        related="company_id.treatment_incentive_percentage",
        readonly=False,
        help="Percentage of the actual paid treatment value allocated to each therapist."
    )
    treatment_incentive_monthly_target = fields.Monetary(
        string="Monthly Incentive Amount Target",
        related="company_id.treatment_incentive_monthly_target",
        currency_field="company_currency_id",
        readonly=False,
        help="Target for accumulated percentage-based incentive, not total treatment revenue. The target bonus is excluded from the target calculation."
    )
    treatment_incentive_target_bonus_amount = fields.Monetary(
        string="Bonus for Achieving Target",
        related="company_id.treatment_incentive_target_bonus_amount",
        currency_field="company_currency_id",
        readonly=False,
        help="Extra amount added to incentive when the employee's accumulated percentage-based incentive reaches the configured incentive target. Keep this at zero until the bonus is decided."
    )
