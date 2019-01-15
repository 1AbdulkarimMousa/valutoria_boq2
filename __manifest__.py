{
    'name': "BOQ - Bill of Quantities",
    'version': '18.0.1.0.0',
    'category': 'Construction/BOQ',
    'summary': 'Complete BOQ Management for Contracting Industry',
    'description': """
        Comprehensive Bill of Quantities management system for construction 
        projects with progress billing, variations, and subcontracting.
        
        Key Features:
        - BOQ Creation from CRM Opportunities
        - Activity Lines with Sub-activities
        - Costing with Materials, Labor, and Equipment
        - Margin Management
        - Advanced Payment Processing
        - Progress Billing / Payment Certificates
        - Variation Orders with Approval Workflow
        - Subcontracting Flow
        - Retention Management
        - Project P&L Tracking
        - Multi-company Support
    """,
    'author': "BOQ Solutions",
    'website': "https://www.boqsolutions.com",
    
    'depends': [
        'base',
        'project', 
        'sale_management',
        'purchase',
        'account',
        'crm',
        'stock',
        'hr_timesheet',
        'portal',
        'mail',
    ],
    
    'data': [
        # Security
        'security/boq_security.xml',
        'security/ir.model.access.csv',
        
        # Data
        'data/boq_sequence.xml',
        'data/boq_journals.xml',
        'data/cost_types.xml',
        
        # Views
        'views/boq_menus.xml',
        'views/boq_project_views.xml',
        'views/boq_activity_views.xml',
        'views/boq_payment_certificate_views.xml',
        'views/boq_variation_views.xml',
        'views/crm_lead_views.xml',
        'views/sale_order_views.xml',
        'views/purchase_order_views.xml',
        
        # Wizards
        'wizards/set_margin_wizard_views.xml',
        'wizards/advance_payment_wizard_views.xml',
        'wizards/subcontract_wizard_views.xml',
        
        # Reports
        'reports/boq_reports.xml',
        'reports/payment_certificate_report.xml',
    ],
    
    'assets': {
        'web.assets_backend': [
            'boq/static/src/css/boq_styles.css',
            'boq/static/src/js/boq_widgets.js',
        ],
    },
    
    'demo': [
        'demo/demo_data.xml',
    ],
    
    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'OPL-1',
}