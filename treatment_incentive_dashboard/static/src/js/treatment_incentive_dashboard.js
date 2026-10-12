/** @odoo-module **/
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, useState } from "@odoo/owl";

export class TreatmentIncentiveDashboard extends Component {
    static template = "treatment_incentive_dashboard.Dashboard";

    setup() {
        this.orm = useService("orm");
        this.action = useService("action");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: false,
            monthLabel: "",
            companyName: "",
            percentage: 0,
            targetAmount: 0,
            currencyCode: "INR",
            currencySymbol: "₹",
            employeeCount: 0,
            employees: [],
            lastUpdated: "",
        });
        onWillStart(() => this.loadData());
    }

    async loadData() {
        this.state.loading = true;
        this.state.error = false;
        try {
            const data = await this.orm.call(
                "treatment.incentive.history",
                "get_incentive_dashboard_data",
                []
            );
            this.state.monthLabel = data.month_label || "";
            this.state.companyName = data.company_name || "";
            this.state.percentage = data.incentive_percentage || 0;
            this.state.targetAmount = data.target_amount || 0;
            this.state.currencyCode = data.currency_code || "INR";
            this.state.currencySymbol = data.currency_symbol || "₹";
            this.state.employeeCount = data.employee_count || 0;
            this.state.employees = data.employees || [];
            this.state.lastUpdated = new Date().toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
            });
        } catch (error) {
            this.state.error = true;
            this.notification.add(
                "Unable to load incentive dashboard. Check the incentive module installation and user access rights.",
                { type: "danger" }
            );
            console.error("Treatment incentive dashboard error:", error);
        } finally {
            this.state.loading = false;
        }
    }

    formatMoney(value) {
        try {
            return new Intl.NumberFormat(undefined, {
                style: "currency",
                currency: this.state.currencyCode || "INR",
                maximumFractionDigits: 2,
            }).format(value || 0);
        } catch {
            return `${this.state.currencySymbol}${Number(value || 0).toFixed(2)}`;
        }
    }

    formatPercentage(value) {
        return `${Number(value || 0).toLocaleString(undefined, {
            maximumFractionDigits: 2,
        })}%`;
    }

    openEmployee(employee) {
        this.action.doAction({
            type: "ir.actions.act_window",
            name: employee.name,
            res_model: "hr.employee",
            res_id: employee.id,
            views: [[false, "form"]],
            view_mode: "form",
            target: "current",
        });
    }

    openHistory(employee) {
        const today = new Date();
        const month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, "0")}`;
        const domain = [
            ["period_key", "=", month],
            ["employee_id", "=", employee.id],
        ];
        this.action.doAction({
            type: "ir.actions.act_window",
            name: `${employee.name} · ${this.state.monthLabel} Incentive History`,
            res_model: "treatment.incentive.history",
            views: [[false, "list"], [false, "form"]],
            view_mode: "list,form",
            domain,
            target: "current",
        });
    }
}

registry.category("actions").add(
    "treatment_incentive_dashboard.client_action",
    TreatmentIncentiveDashboard
);
