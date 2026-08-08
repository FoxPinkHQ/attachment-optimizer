{
    "name": "Attachment Optimizer",
    "version": "17.0.1.0.7",
    "category": "Storage",
    "summary": "Safely replicate and serve Odoo attachments from S3-compatible storage.",
    "description": """
        Analyze Odoo attachment storage and replicate selected attachments to
        S3-compatible object storage with checksum verification, audit logging,
        retry support, and filestore fallback.
    """,
    "author": "FoxPink",
    "support": "aduy000@gmail.com",
    "website": "https://github.com/FoxPinkHQ/attachment-optimizer",
    "license": "LGPL-3",
    "images": [
        "static/description/preview.png",
    ],
    "depends": [
        "base",
        "web",
    ],
    "external_dependencies": {
        "python": ["boto3"],
    },
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "security/record_rules.xml",
        "views/res_config_settings_views.xml",
        "views/storage_mapping_views.xml",
        "views/dashboard_menu.xml",
        "views/migration_views.xml",
        "views/audit_log_views.xml",
        "wizard/views/migration_confirm_views.xml",
        "data/recovery_cron.xml",
    ],
    "demo": [
        "demo/attachment_optimizer_demo.xml",
    ],
    "assets": {
        "web.assets_backend": [
            "attachment_optimizer/static/src/components/dashboard/dashboard.js",
            "attachment_optimizer/static/src/components/dashboard/dashboard.xml",
            "attachment_optimizer/static/src/components/dashboard/dashboard.scss",
        ],
    },
    "installable": True,
    "application": True,
    "auto_install": False,
    "post_init_hook": "_post_init_hook",
    "uninstall_hook": "_uninstall_hook",
}
