from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TreatmentIncentiveHistory(models.Model):
    _name = "treatment.incentive.history"
    _description = "Employee Treatment Incentive History"
    _order = "treatment_date desc, id desc"
    _rec_name = "booking_id"

    company_id = fields.Many2one("res.company", string="Company", required=True, readonly=True, index=True, default=lambda self: self.env.company)
    employee_id = fields.Many2one("hr.employee", string="Therapist", required=True, index=True, ondelete="restrict")
    booking_id = fields.Many2one("treatment.booking", string="Treatment Booking", required=True, index=True, ondelete="restrict")
    customer_id = fields.Many2one("res.partner", string="Booking Customer", readonly=True, ondelete="restrict")
    service_id = fields.Many2one("treatment.service", string="Service", readonly=True, ondelete="restrict")
    booking_type = fields.Selection([
        ("normal", "Normal Booking"),
        ("plan", "Treatment Plan"),
    ], string="Booking Type", readonly=True)
    plan_purchase_id = fields.Many2one("treatment.plan.purchase", string="Treatment Plan", readonly=True, ondelete="restrict")
    treatment_date = fields.Date(required=True, readonly=True, index=True)
    currency_id = fields.Many2one("res.currency", required=True, readonly=True)
    paid_amount_basis = fields.Monetary(
        string="Paid Amount for Treatment",
        currency_field="currency_id",
        required=True,
        readonly=True,
        help="Actual amount paid for a normal treatment or the amount allocated per included plan session, capped at the session's full plan value."
    )
    therapist_count = fields.Integer(string="Therapist Count", required=True, readonly=True)
    treatment_amount = fields.Monetary(
        string="Paid Amount per Therapist",
        currency_field="currency_id",
        required=True,
        readonly=True,
        help="Actual paid treatment value divided equally among assigned therapists. Incentive target progress is based on this amount."
    )
    incentive_percentage = fields.Float(string="Incentive %", required=True, readonly=True)
    percentage_incentive_amount = fields.Monetary(
        string="Percentage Incentive",
        currency_field="currency_id",
        required=True,
        readonly=True,
        default=0.0,
        help="Incentive calculated from the therapist's allocated paid treatment amount and configured percentage, excluding target bonus."
    )
    target_bonus_amount = fields.Monetary(
        string="Target Achievement Bonus",
        currency_field="currency_id",
        required=True,
        readonly=True,
        default=0.0,
        help="One-time extra bonus attached to the treatment entry that reaches the target in a cycle."
    )
    incentive_amount = fields.Monetary(
        string="Total Incentive",
        currency_field="currency_id",
        required=True,
        readonly=True,
        help="Percentage incentive plus any target achievement bonus."
    )
    period_key = fields.Char(string="Month", required=True, index=True, readonly=True, help="Calendar month in YYYY-MM format.")
    year = fields.Integer(required=True, index=True, readonly=True)
    month_number = fields.Integer(string="Month Number", required=True, index=True, readonly=True)

    # New amount-based target fields. Old count columns remain in the database
    # for upgrade compatibility but are no longer used for target logic.
    target_amount = fields.Monetary(
        string="Monthly Incentive Target",
        currency_field="currency_id",
        readonly=True,
        help="Configured monthly incentive target snapshot for this employee's incentive cycle."
    )
    target_cycle = fields.Integer(string="Target Cycle", readonly=True)
    cycle_paid_amount = fields.Monetary(
        string="Accumulated Incentive in Target Cycle",
        currency_field="currency_id",
        readonly=True,
        help="Accumulated percentage-based incentive for this target cycle. Target bonuses are excluded from this calculation."
    )
    target_achieved = fields.Boolean(string="Target Achieved", readonly=True)
    target_progress = fields.Char(string="Target Progress", compute="_compute_target_progress")

    # Legacy fields kept temporarily so an existing database can be upgraded
    # without dropping columns; they are not displayed or used for target logic.
    target_count = fields.Integer(string="Legacy Treatment Count Target", readonly=True)
    cycle_treatment_count = fields.Integer(string="Legacy Cycle Treatment Count", readonly=True)

    _sql_constraints = [
        ("booking_employee_unique", "unique(booking_id, employee_id)",
         "A treatment incentive history entry already exists for this therapist and booking.")
    ]

    @api.depends("cycle_paid_amount", "target_amount", "target_achieved")
    def _compute_target_progress(self):
        for rec in self:
            amount = rec.cycle_paid_amount or 0.0
            target = rec.target_amount or 0.0
            if target > 0:
                rec.target_progress = "%s / %s%s" % (
                    rec.currency_id.format(amount),
                    rec.currency_id.format(target),
                    _(" (Achieved)") if rec.target_achieved else "",
                )
            else:
                rec.target_progress = _("%s; no target configured") % rec.currency_id.format(amount)

    @api.model_create_multi
    def create(self, vals_list):
        """Snapshot company settings, then recalculate amount-based target cycles."""
        prepared = []
        for incoming in vals_list:
            vals = dict(incoming)
            employee = self.env["hr.employee"].browse(vals.get("employee_id")).exists()
            company = self.env["res.company"].browse(vals.get("company_id")).exists()
            if not company:
                company = employee.company_id if employee and employee.company_id else self.env.company

            date_value = fields.Date.to_date(vals.get("treatment_date") or fields.Date.context_today(self))
            vals.setdefault("company_id", company.id)
            vals.setdefault("treatment_date", date_value)
            vals.setdefault("period_key", date_value.strftime("%Y-%m"))
            vals.setdefault("year", date_value.year)
            vals.setdefault("month_number", date_value.month)
            vals.setdefault("incentive_percentage", company.treatment_incentive_percentage)
            vals.setdefault("target_amount", company.treatment_incentive_monthly_target)
            percentage_amount = vals.get(
                "percentage_incentive_amount",
                (vals.get("treatment_amount", 0.0) or 0.0)
                * (vals.get("incentive_percentage", company.treatment_incentive_percentage) or 0.0)
                / 100.0,
            )
            vals.setdefault("percentage_incentive_amount", percentage_amount)
            vals.setdefault("target_bonus_amount", 0.0)
            vals.setdefault("incentive_amount", percentage_amount + (vals.get("target_bonus_amount", 0.0) or 0.0))
            prepared.append(vals)

        records = super().create(prepared)
        records._recompute_target_cycles()
        return records

    def write(self, vals):
        result = super().write(vals)
        if not self.env.context.get("skip_incentive_target_recompute") and any(
            field_name in vals for field_name in (
                "treatment_amount", "percentage_incentive_amount", "incentive_percentage",
                "treatment_date", "employee_id", "company_id", "target_amount"
            )
        ):
            self._recompute_target_cycles()
        return result

    def _recompute_target_cycles(self):
        """Rebuild each employee's monthly target cycles from percentage-incentive snapshots."""
        groups = {}
        for rec in self:
            if rec.employee_id and rec.period_key and rec.company_id:
                groups[(rec.employee_id.id, rec.company_id.id, rec.period_key)] = True

        History = self.env["treatment.incentive.history"].sudo()
        for employee_id, company_id, period_key in groups:
            records = History.search([
                ("employee_id", "=", employee_id),
                ("company_id", "=", company_id),
                ("period_key", "=", period_key),
            ], order="treatment_date asc, id asc")

            cycle_number = 1
            cycle_amount = 0.0
            for rec in records:
                target = rec.target_amount or 0.0
                # Historical rows from versions that used a treatment-count
                # target have no amount target snapshot. Keep them visible but
                # exclude them from the new amount-based cycle calculations.
                if target <= 0:
                    percentage_amount = rec.percentage_incentive_amount or (
                        (rec.treatment_amount or 0.0) * (rec.incentive_percentage or 0.0) / 100.0
                    )
                    rec.with_context(skip_incentive_target_recompute=True).write({
                        "target_cycle": 0,
                        "cycle_paid_amount": 0.0,
                        "target_achieved": False,
                        "percentage_incentive_amount": percentage_amount,
                        "target_bonus_amount": 0.0,
                        "incentive_amount": percentage_amount,
                    })
                    continue

                # A completed incentive-target cycle resets before the next
                # qualifying treatment. The treatment that crosses the target
                # remains in the completed cycle; the following one starts at
                # zero. Only percentage-based incentive is accumulated here;
                # the bonus must not itself help reach the target.
                if cycle_amount >= target:
                    cycle_number += 1
                    cycle_amount = 0.0

                percentage_amount = rec.percentage_incentive_amount or (
                    (rec.treatment_amount or 0.0) * (rec.incentive_percentage or 0.0) / 100.0
                )
                cycle_amount += percentage_amount
                achieved = cycle_amount >= target
                # Only the row that first reaches the target in its cycle is
                # eligible for the bonus. Keep the saved bonus on that row if
                # recalculating its target cycle later; do not duplicate it.
                if not achieved:
                    bonus_amount = 0.0
                elif rec.target_achieved:
                    bonus_amount = rec.target_bonus_amount or 0.0
                else:
                    bonus_amount = rec.company_id.treatment_incentive_target_bonus_amount or 0.0

                rec.with_context(skip_incentive_target_recompute=True).write({
                    "target_cycle": cycle_number,
                    "cycle_paid_amount": cycle_amount,
                    "target_achieved": achieved,
                    "percentage_incentive_amount": percentage_amount,
                    "target_bonus_amount": bonus_amount,
                    "incentive_amount": percentage_amount + bonus_amount,
                })

    @api.constrains("paid_amount_basis", "treatment_amount", "incentive_percentage", "percentage_incentive_amount", "target_bonus_amount", "incentive_amount", "target_amount", "cycle_paid_amount")
    def _check_values(self):
        for rec in self:
            if min(rec.paid_amount_basis, rec.treatment_amount, rec.percentage_incentive_amount, rec.target_bonus_amount, rec.incentive_amount, rec.target_amount, rec.cycle_paid_amount) < 0:
                raise ValidationError(_("Paid treatment amounts, target amount, and incentive amount cannot be negative."))
            if rec.incentive_percentage < 0:
                raise ValidationError(_("Incentive percentage cannot be negative."))

    def action_open_booking(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Treatment Booking"),
            "res_model": "treatment.booking",
            "view_mode": "form",
            "res_id": self.booking_id.id,
            "target": "current",
        }
