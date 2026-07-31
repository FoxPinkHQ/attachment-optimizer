from odoo import SUPERUSER_ID, api
from . import models
from . import wizard


def _hook_env(env_or_cr, registry=None):
    if registry is None:
        return env_or_cr
    return api.Environment(env_or_cr, SUPERUSER_ID, {})

def _post_init_hook(env_or_cr, registry=None):
    env = _hook_env(env_or_cr, registry)
    group = env.ref('attachment_optimizer.group_storage_optimization_manager', raise_if_not_found=False)
    if group:
        base_user = env.ref('base.group_user')
        group.implied_ids = [(4, base_user.id)]
        admin = env.ref('base.user_admin')
        group.users = [(4, admin.id)]


def _uninstall_hook(env_or_cr, registry=None):
    env = _hook_env(env_or_cr, registry)
    env['ir.config_parameter'].sudo().search([
        ('key', '=like', 'attachment_storage.%'),
    ]).unlink()
