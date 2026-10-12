from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class TreatmentWorkingHours(models.Model):
    _name = "treatment.working.hours"
    _description = "Treatment Working Hours"
    _order = "weekday"
    _rec_name = "weekday"

    weekday = fields.Selection([
        ("0", "Monday"), ("1", "Tuesday"), ("2", "Wednesday"),
        ("3", "Thursday"), ("4", "Friday"), ("5", "Saturday"),
        ("6", "Sunday"),
    ], required=True, index=True)
    is_closed = fields.Boolean(string="Closed", default=False)
    start_hour = fields.Float(string="Opening Time", default=7.0, required=True, help="24-hour time, e.g. 7.5 means 7:30 AM.")
    end_hour = fields.Float(string="Closing Time", default=19.0, required=True, help="24-hour time, e.g. 18.5 means 6:30 PM.")

    _sql_constraints = [("weekday_unique", "unique(weekday)", "Working hours can only be configured once per weekday.")]

    @api.constrains("start_hour", "end_hour", "is_closed")
    def _check_hours(self):
        for rec in self:
            if not rec.is_closed and (rec.start_hour < 0 or rec.end_hour > 24 or rec.end_hour <= rec.start_hour):
                raise ValidationError(_("Closing time must be later than opening time and both must be within 00:00–24:00."))
