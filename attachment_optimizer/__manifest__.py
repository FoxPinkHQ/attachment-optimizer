{
    "name": "Attachment Optimizer",
    "version": "19.0.2.1.0",
    "category": "Storage",
    "summary": "Analyze attachment storage and migrate files to S3-compatible object storage.",
    "description": """
        Analyze Odoo attachment storage usage and migrate selected attachments
        to S3-compatible object storage to reduce filestore footprint.
    """,
    "author": "FoxPink",
    "website": "https://github.com/FoxPinkHQ/attachment-optimizer",
    "license": "LGPL-3",
    "images": [
        "static/description/preview.png",
    ],
    "depends": [
        "base",
        "web",
    ],
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
}
