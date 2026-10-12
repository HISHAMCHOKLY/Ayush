from odoo import api, fields, models


class TreatmentIncentiveHistory(models.Model):
    _inherit = "treatment.incentive.history"

    @api.model
    def get_incentive_dashboard_data(self):
        """Return current-calendar-month incentive totals for the active company."""
        company = self.env.company
        today = fields.Date.context_today(self)
        period_key = today.strftime("%Y-%m")
        month_label = today.strftime("%B %Y")

        History = self.sudo()
        records = History.search([
            ("company_id", "=", company.id),
            ("period_key", "=", period_key),
        ], order="treatment_date asc, id asc")

        employees = self.env["hr.employee"].sudo().search([
            ("company_id", "=", company.id),
            ("active", "=", True),
        ], order="name")

        employee_data = {}
        for employee in employees:
            employee_data[employee.id] = {
                "id": employee.id,
                "name": employee.name,
                "treatment_count": 0,
                "incentive_amount": 0.0,
                "paid_amount": 0.0,
                "target_amount": company.treatment_incentive_monthly_target or 0.0,
                "cycle_paid_amount": 0.0,
                "target_achieved": False,
            }

        history_by_employee = {}
        for record in records:
            employee = record.employee_id
            if not employee:
                continue
            if employee.id not in employee_data:
                employee_data[employee.id] = {
                    "id": employee.id,
                    "name": employee.name,
                    "treatment_count": 0,
                    "incentive_amount": 0.0,
                    "paid_amount": 0.0,
                    "target_amount": company.treatment_incentive_monthly_target or 0.0,
                    "cycle_paid_amount": 0.0,
                    "target_achieved": False,
                }
            row = employee_data[employee.id]
            row["treatment_count"] += 1
            row["incentive_amount"] += record.incentive_amount or 0.0
            # This dashboard's target tracks accumulated percentage incentive,
            # not treatment revenue. The history's cycle_paid_amount field is
            # retained technically for upgrade compatibility but now stores
            # the accumulated base incentive for the current target cycle.
            history_by_employee.setdefault(employee.id, []).append(record)

        current_target = company.treatment_incentive_monthly_target or 0.0
        for employee_id, employee_records in history_by_employee.items():
            latest = employee_records[-1]
            latest_cycle = latest.target_cycle or 0
            cycle_total = latest.cycle_paid_amount or 0.0 if latest_cycle else 0.0
            employee_data[employee_id]["cycle_paid_amount"] = cycle_total
            employee_data[employee_id]["target_achieved"] = bool(
                current_target > 0 and cycle_total >= current_target
            )

        result_rows = sorted(
            employee_data.values(),
            key=lambda row: (-row["incentive_amount"], row["name"].lower())
        )
        currency = company.currency_id
        return {
            "company_name": company.name,
            "month_label": month_label,
            "period_key": period_key,
            "incentive_percentage": company.treatment_incentive_percentage or 0.0,
            "target_amount": current_target,
            "currency_code": currency.name or "INR",
            "currency_symbol": currency.symbol or currency.name or "₹",
            "employee_count": len(result_rows),
            "employees": result_rows,
        }
