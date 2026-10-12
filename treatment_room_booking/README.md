# Treatment Room Booking Dashboard (Odoo 18)

A custom Odoo 18 module providing a room-wise schedule with **time on the horizontal axis** (7:00 AM–7:00 PM) and **rooms on the vertical axis**. It includes a client-action OWL dashboard, room/service setup, bookings, automatic refresh, clickable timeline creation, and overlap validation that includes cleaning buffers.

## Install
1. Copy `treatment_room_booking` into an Odoo 18 custom addons directory.
2. Restart the Odoo service.
3. Enable developer mode and update the Apps list.
4. Install **Treatment Room Booking Dashboard**.
5. Open **Treatment Booking → Room Dashboard**.

Four sample rooms and two example treatments are created on first installation. Change or archive these from Treatment Booking → Rooms and Treatments / Services.

## Booking workflow
- Click an empty part of a room timeline to open a booking form with room and start time prefilled.
- Choose customer, treatment and therapist. The service's duration and cleaning buffer are suggested automatically.
- Save the booking; the dashboard refreshes on closing the form and every 15 seconds.
- Click an existing booking block to open its record.
- Booking overlaps in the same room are rejected, including cleaning buffers. Cancelled bookings do not block a room.

## Important notes
- This is a starting custom module and has not been installed against your specific Odoo database in this environment. Test on a staging database before production use.
- Dashboard time display follows the browser's local timezone. For deployments with users in multiple timezones, validate date-boundary behavior with your Odoo timezone configuration.
- The module uses its own models (`treatment.room`, `treatment.service`, `treatment.booking`) and does not integrate automatically with any existing spa/appointment module. If you already have booking models, adapt it to avoid duplicate data.
- User-level access is currently granted to internal users; tighten access groups/record rules as needed for your organization.

## Day-wise working hours (Odoo 18)

Open **Treatment Booking → Working Hours** to configure the schedule for each weekday. Each weekday has an opening time, closing time, and a Closed checkbox. Defaults are Monday–Saturday 07:00–19:00 and Sunday closed; adjust them to your center's schedule. The dashboard reads the selected date's weekday schedule, adjusts the horizontal time axis, and shows a closed-day notice when appropriate. Booking validation also checks the configured weekday hours and prevents bookings outside them.

Times are entered with Odoo's float-time widget (for example, 7.5 = 07:30 and 18.5 = 18:30).


Update: receipt payments create and post an Odoo customer payment against a Cash/Bank journal. Payment and inventory records are opened through smart buttons; the embedded tabs are removed. Booking payment status is based only on posted custom payment records.
