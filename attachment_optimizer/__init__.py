from . import models
from . import wizard


def _post_init_hook(env):
    group = env.ref('attachment_optimizer.group_storage_optimization_manager', raise_if_not_found=False)
    if group:
        users = env.ref('base.group_user')
        group.implied_ids = [(4, users.id)]
        admin = env.ref('base.user_admin')
        group.users = [(4, admin.id)]

