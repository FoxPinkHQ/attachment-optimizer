from . import models
from . import wizard


def _post_init_hook(env):
    group = env.ref('attachment_optimizer.group_storage_optimization_manager', raise_if_not_found=False)
    if group:
        base_user = env.ref('base.group_user')
        group.implied_ids = [(4, base_user.id)]
        admin = env.ref('base.user_admin')
        group.user_ids = [(4, admin.id)]


def _uninstall_hook(env):
    env['ir.config_parameter'].sudo().search([
        ('key', '=like', 'attachment_storage.%'),
    ]).unlink()
