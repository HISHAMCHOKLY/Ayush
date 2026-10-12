/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";


function parseServerDate(value) {
    if (!value) return null;
    // Odoo datetime fields are stored/returned in UTC; convert to browser local time.
    return new Date(value.replace(" ", "T") + "Z");
}
function dateKey(date) {
    return `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,"0")}-${String(date.getDate()).padStart(2,"0")}`;
}
function utcDateTimeString(date) {
    // `date` is constructed in the browser's local timezone from the selected
    // timeline wall-clock time. toISOString() converts that instant to UTC;
    // send the UTC-naive value expected by Odoo's datetime context defaults.
    return date.toISOString().slice(0, 19).replace("T", " ");
}

export class TreatmentRoomDashboard extends Component {
    static template = "treatment_room_booking.Dashboard";
    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({ date: dateKey(new Date()), rooms: [], services: [], bookings: [], todayCount: 0, monthCount: 0, workingHours: { start_hour: 7, end_hour: 19, is_closed: false, weekday: "" }, loading: true, lastUpdated: "" });
        this.refreshTimer = null;
        onWillStart(() => this.loadData());
        onWillUnmount(() => clearInterval(this.refreshTimer));
        this.refreshTimer = setInterval(() => this.loadData(), 15000);
    }
    async loadData() {
        this.state.loading = true;
        try {
            const data = await this.orm.call("treatment.booking", "get_dashboard_data", [this.state.date]);
            this.state.rooms = data.rooms || [];
            this.state.services = data.services || [];
            this.state.todayCount = data.today_count || 0;
            this.state.monthCount = data.month_count || 0;
            this.state.workingHours = data.working_hours || { start_hour: 7, end_hour: 19, is_closed: false, weekday: "" };
            this.state.bookings = (data.bookings || []).map((booking) => {
                const start = parseServerDate(booking.start_datetime);
                const end = parseServerDate(booking.end_datetime);
                const customer = Array.isArray(booking.customer_id) ? booking.customer_id[1] : "";
                const service = booking.service_names || (Array.isArray(booking.service_id) ? booking.service_id[1] : "Treatment");
                const mobile = booking.mobile_number || booking.contact_number || "";
                const roomId = Array.isArray(booking.room_id) ? booking.room_id[0] : booking.room_id;
                return { ...booking, start, end, customer, service, mobile, roomId, dashboardStatus: booking.dashboard_status || booking.state,
                    visible: start && dateKey(start) === this.state.date,
                    left: start ? Math.max(0, (this.minutesFromOpening(start)) / this.totalMinutes * 100) : 0,
                    width: start && end ? Math.max(0.7, Math.min(100, (Math.min(this.minutesFromClosing(end), this.totalMinutes) - Math.max(this.minutesFromOpening(start), 0)) / this.totalMinutes * 100)) : 1,
                    timeLabel: start && end ? `${this.formatTime(start)}–${this.formatTime(end)}` : "",
                };
            }).filter((b) => b.visible && b.end && this.minutesFromOpening(b.end) > 0 && this.minutesFromOpening(b.start) < this.totalMinutes);
            this.state.lastUpdated = new Date().toLocaleTimeString([], {hour:"2-digit", minute:"2-digit", second:"2-digit"});
        } catch (error) {
            this.notification.add("Unable to load the treatment schedule. Check access rights and server logs.", { type: "danger" });
            console.error(error);
        } finally { this.state.loading = false; }
    }
    formatTime(date) { return date.toLocaleTimeString([], {hour: "numeric", minute: "2-digit"}); }
    get startMinute() { return Math.round(Number(this.state.workingHours.start_hour || 0) * 60); }
    get endMinute() { return Math.round(Number(this.state.workingHours.end_hour || 0) * 60); }
    get totalMinutes() { return Math.max(60, this.endMinute - this.startMinute); }
    get workingHoursLabel() { return this.state.workingHours.is_closed ? `Closed · ${this.state.workingHours.weekday}` : `${this.timeFromMinutes(this.startMinute)} – ${this.timeFromMinutes(this.endMinute)}`; }
    get closingTimeLabel() { return this.timeFromMinutes(this.endMinute); }
    timeFromMinutes(minute) { const d = new Date(2000, 0, 1, Math.floor(minute / 60), minute % 60); return d.toLocaleTimeString([], {hour: "numeric", minute: minute % 60 ? "2-digit" : undefined}); }
    minutesFromOpening(date) { return date.getHours() * 60 + date.getMinutes() - this.startMinute; }
    minutesFromClosing(date) { return date.getHours() * 60 + date.getMinutes() - this.startMinute; }
    get hours() {
        if (this.state.workingHours.is_closed) return [];
        const result = [];
        for (let minute = this.startMinute; minute < this.endMinute; minute += 60) {
            const hour = Math.floor(minute / 60), mins = minute % 60;
            const d = new Date(2000, 0, 1, hour, mins);
            result.push({ label: d.toLocaleTimeString([], {hour: "numeric", minute: mins ? "2-digit" : undefined}), left: (minute - this.startMinute) / this.totalMinutes * 100 });
        }
        return result;
    }
    bookingsFor(roomId) { return this.state.bookings.filter((b) => b.roomId === roomId); }
    previousDay() { this.changeDate(-1); }
    nextDay() { this.changeDate(1); }
    today() { this.state.date = dateKey(new Date()); this.loadData(); }
    changeDate(days) { const d = new Date(`${this.state.date}T12:00:00`); d.setDate(d.getDate()+days); this.state.date = dateKey(d); this.loadData(); }
    onDateChange(ev) { if (ev.target.value) { this.state.date = ev.target.value; this.loadData(); } }
    async clickTimeline(ev, room) {
        if (ev.target.closest(".trb-booking")) return;
        const rect = ev.currentTarget.getBoundingClientRect();
        const offset = Math.max(0, Math.min(rect.width, ev.clientX - rect.left));
        if (this.state.workingHours.is_closed) {
            this.notification.add("The treatment center is closed on this day. Configure Working Hours to open it.", { type: "warning" });
            return;
        }
        const minute = Math.round((offset / rect.width * this.totalMinutes) / 15) * 15;
        const start = new Date(`${this.state.date}T00:00:00`);
        start.setMinutes(this.startMinute + minute);
        if (start.getHours() * 60 + start.getMinutes() >= this.endMinute) {
            this.notification.add("Please choose a time before closing.", { type: "warning" });
            return;
        }
        const busy = this.bookingsFor(room.id).some((b) => {
            const busyEnd = new Date(b.end.getTime() + (Number(b.cleaning_minutes || 0) * 60000));
            return start >= b.start && start < busyEnd || start < b.start && start.getTime()+15*60000 > b.start.getTime();
        });
        if (busy) {
            this.notification.add("That time overlaps an existing booking or cleaning buffer.", { type: "warning" });
            return;
        }
        await this.action.doAction({ type: "ir.actions.act_window", name: "New Treatment Booking", res_model: "treatment.booking", views: [[false,"form"]], view_mode: "form", target: "new", context: { default_room_id: room.id, default_start_datetime: utcDateTimeString(start), default_state: "draft" } }, { onClose: () => this.loadData() });
    }
    openBooking(booking) {
        this.action.doAction({ type: "ir.actions.act_window", name: booking.name, res_model: "treatment.booking", res_id: booking.id, views: [[false,"form"]], view_mode: "form", target: "new" }, { onClose: () => this.loadData() });
    }
    newBooking() {
        const start = new Date(`${this.state.date}T00:00:00`);
        start.setMinutes(this.startMinute);
        this.action.doAction({ type: "ir.actions.act_window", name: "New Treatment Booking", res_model: "treatment.booking", views: [[false,"form"]], view_mode: "form", target: "new", context: { default_start_datetime: utcDateTimeString(start), default_state: "draft" } }, { onClose: () => this.loadData() });
    }
}
registry.category("actions").add("treatment_room_booking.dashboard", TreatmentRoomDashboard);
