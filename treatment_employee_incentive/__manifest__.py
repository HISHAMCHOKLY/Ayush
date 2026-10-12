{
    "name": "Treatment Employee Incentives",
    "version": "18.0.1.0.0",
    "category": "Human Resources",
    "summary": "Employee treatment history and incentive tracking",
    "description": """
Tracks completed treatments by therapist, calculates incentives from the treatment amount,
supports treatment-plan per-session value, stores a permanent incentive history, and provides
employee/month/year performance reporting.
    """,
    "author": "Custom Development",
    "license": "LGPL-3",
    "depends": [
        "treatment_room_booking",
        "treatment_plan_management",
        "hr",
        "base_setup"
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_config_settings_views.xml",
        "views/treatment_incentive_history_views.xml",
        "views/hr_employee_views.xml"
    ],
    "application": True,
    "installable": True
}
