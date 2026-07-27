from datetime import date
from calendar import monthrange
from odoo import api, fields, models


class HrEmployee(models.Model):
    _inherit = "hr.employee"

    treatment_ids = fields.One2many(
        "salon.order", 'employee_id',
        compute="_compute_monthly_treatments",
        string="Current Month Treatments",
    )
    treatment_count = fields.Integer(compute="_compute_monthly_treatments", string="Total Treatments")
    monthly_treatment_count = fields.Integer(compute="_compute_monthly_treatments")

    month_commission_amount = fields.Float(
        string="This Month Commission",
        compute="_compute_monthly_treatments",
    )
    total_commission_amount = fields.Float(
        string="Total Commission",
        compute="_compute_monthly_treatments",
    )

    @api.depends()
    def _compute_monthly_treatments(self):
        commission = 0.0
        monthly_commission = 0.0
        today = date.today()
        first = today.replace(day=1)
        last = today.replace(day=monthrange(today.year, today.month)[1])
        for emp in self:
            salon_orders = self.env["salon.order"].search([
                ('employee_ids', 'in', emp.ids)
            ])
            emp.treatment_ids = salon_orders
            month_salon_orders = self.env["salon.order"].search([
                ('employee_ids', 'in', emp.ids),
                ("date", ">=", first),
                ("date", "<=", last),
            ])
            emp.monthly_treatment_count = len(month_salon_orders)
            emp.treatment_count = len(salon_orders)
            for monthly_order in month_salon_orders:

                employee_count = len(monthly_order.employee_ids)

                if not employee_count:
                    continue

                for line in monthly_order.order_line_ids:
                    percentage = line.product_id.commission_percentage

                    total_commission = (
                            line.price * percentage / 100
                    )

                    monthly_commission += total_commission / employee_count

            emp.month_commission_amount = monthly_commission

            for order in salon_orders:

                employee_count = len(order.employee_ids)

                if not employee_count:
                    continue

                for line in order.order_line_ids:
                    percentage = line.product_id.commission_percentage

                    total_commission = (
                            line.price * percentage / 100
                    )

                    commission += total_commission / employee_count

            emp.total_commission_amount = commission


class ProductTemplate(models.Model):
    _inherit = "product.template"

    commission_percentage = fields.Float(
        string="Commission %",
        digits=(16, 2),
        default=0.0,
        help="Commission percentage for this Treatment."
    )
