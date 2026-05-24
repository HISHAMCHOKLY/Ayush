# -*- coding: utf-8 -*-
{
    'name': 'Treatment Management Plan',
    'version': '18.0.1.0.0',
    'category': 'Services',
    'summary': 'Add Plan Master and Plan Treatment Order features',
    'description': 'This module adds the ability to create Treatment plans and automatically generate Treatment orders for a specified date range.',
    'depends': ['salon_management'],
    'data': [
        'security/ir.model.access.csv',
        'data/salon_plan_sequence.xml',
        'views/salon_plan_master_views.xml',
        'views/salon_plan_order_views.xml',
        'views/salon_order_views.xml',
    ],
    'installable': True,
    'application': False,
    'auto_install': False,
}
