{
    "name": "Attachment Optimizer",
    "version": "18.0.1.0.0",
    "category": "Storage",
    "summary": "Analyze attachment storage and migrate files to S3-compatible object storage.",
    "description": """
        Analyze Odoo attachment storage usage and migrate selected attachments
        to S3-compatible object storage to reduce filestore footprint.
    """,
    "author": "FoxPink",
    "website": "https://foxpink.dev",
    "license": "LGPL-3",
    "depends": [
        "base",
        "web",
    ],
    "data": [
        "security/groups.xml",
        "security/ir.model.access.csv",
        "views/storage_mapping_views.xml",
        "views/dashboard_menu.xml",
        "views/migration_views.xml",
        "views/audit_log_views.xml",
    ],
    "demo": [
        "demo/attachment_optimizer_demo.xml",
    ],
    "installable": True,
    "application": False,
    "auto_install": False,
}
