from odoo import fields, models, _


class TreatmentBooking(models.Model):
    _inherit = "treatment.booking"

    def _get_incentive_payment_basis(self):
        """Return the treatment's actual paid-value basis, before therapist split.

        Normal bookings use posted customer receipts. Plan bookings use the
        customer's total paid plan amount spread over all included sessions,
        capped at the plan's unit value. This is recorded when the treatment
        is completed and can be refreshed if a further receipt is registered.
        """
        self.ensure_one()
        if self.state != "done":
            return 0.0

        # A plan booking is covered by a purchase-level payment, rather than
        # by a second payment against this zero-priced service booking.
        if self.booking_type == "plan" and self.plan_purchase_id:
            purchase = self.plan_purchase_id
            if purchase.amount_paid <= 0:
                return 0.0
            total_sessions = purchase.total_sessions or purchase.plan_id.total_sessions
            plan_price = purchase.plan_price or purchase.plan_id.price
            if not total_sessions:
                return 0.0
            paid_per_session = purchase.amount_paid / total_sessions
            plan_unit_price = plan_price / total_sessions
            return max(min(paid_per_session, plan_unit_price), 0.0)

        # Normal service bookings earn incentive only after at least one
        # posted payment, and only while the booking status is Paid/Partial.
        if self.payment_status not in ("paid", "partial"):
            return 0.0
        posted = self.payment_ids.filtered(lambda payment: payment.state == "posted")
        return max(sum(posted.mapped("paid_amount")), 0.0)

    def _sync_treatment_incentive_history(self):
        """Create/update incentive snapshots for Done + Paid/Partially Paid bookings."""
        History = self.env["treatment.incentive.history"].sudo()
        for booking in self:
            if booking.state != "done":
                continue
            employees = booking.therapist_ids
            if not employees:
                continue

            paid_basis = booking._get_incentive_payment_basis()
            if paid_basis <= 0:
                continue
            therapist_count = len(employees)
            allocated_paid_basis = paid_basis / therapist_count

            if booking.end_datetime:
                end_dt = fields.Datetime.to_datetime(booking.end_datetime)
                treatment_date = fields.Datetime.context_timestamp(booking, end_dt).date()
            elif booking.start_datetime:
                start_dt = fields.Datetime.to_datetime(booking.start_datetime)
                treatment_date = fields.Datetime.context_timestamp(booking, start_dt).date()
            else:
                treatment_date = fields.Date.context_today(booking)

            for employee in employees:
                history = History.search([
                    ("booking_id", "=", booking.id),
                    ("employee_id", "=", employee.id),
                ], limit=1)

                values = {
                    "company_id": (employee.company_id or self.env.company).id,
                    "employee_id": employee.id,
                    "booking_id": booking.id,
                    "customer_id": booking.customer_id.id,
                    "service_id": booking.service_id.id,
                    "booking_type": booking.booking_type,
                    "plan_purchase_id": booking.plan_purchase_id.id if booking.plan_purchase_id else False,
                    "treatment_date": treatment_date,
                    "currency_id": (
                        booking.plan_purchase_id.currency_id
                        if booking.booking_type == "plan" and booking.plan_purchase_id
                        else (getattr(booking, "currency_id", False) or booking.service_id.currency_id or self.env.company.currency_id)
                    ).id,
                    "paid_amount_basis": paid_basis,
                    "therapist_count": therapist_count,
                    "treatment_amount": allocated_paid_basis,
                }
                if history:
                    # Preserve the originally recorded percentage and target
                    # cycle. Recalculate only the actual-paid amount and
                    # incentive when additional posted money is received.
                    percentage = history.incentive_percentage
                    percentage_amount = allocated_paid_basis * percentage / 100.0
                    values.update({
                        "incentive_percentage": percentage,
                        "percentage_incentive_amount": percentage_amount,
                        "incentive_amount": percentage_amount + (history.target_bonus_amount or 0.0),
                    })
                    history.write(values)
                else:
                    History.create(values)

    def action_mark_done(self):
        result = super().action_mark_done()
        self._sync_treatment_incentive_history()
        return result


class TreatmentBookingPayment(models.Model):
    _inherit = "treatment.booking.payment"

    def action_register_payment(self):
        result = super().action_register_payment()
        # A booking may already be Done before its next partial/final payment.
        # Re-sync its single history row(s), rather than creating duplicates.
        self.mapped("booking_id")._sync_treatment_incentive_history()
        return result
