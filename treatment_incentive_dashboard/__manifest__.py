{
    "name": "Treatment Incentive Dashboard",
    "version": "18.0.1.0.0",
    "category": "Human Resources",
    "summary": "Current-month employee incentive dashboard",
    "description": "Shows configured incentive percentage and amount target, plus each employee's current-month completed treatment count, earned incentive, and target progress.",
    "author": "Custom Development",
    "license": "LGPL-3",
    "depends": [
        "treatment_employee_incentive",
        "web"
    ],
    "data": [
        "views/treatment_incentive_dashboard_views.xml"
    ],
    "assets": {
        "web.assets_backend": [
            "treatment_incentive_dashboard/static/src/js/treatment_incentive_dashboard.js",
            "treatment_incentive_dashboard/static/src/xml/treatment_incentive_dashboard.xml",
            "treatment_incentive_dashboard/static/src/scss/treatment_incentive_dashboard.scss"
        ]
    },
    "application": True,
    "installable": True
}
