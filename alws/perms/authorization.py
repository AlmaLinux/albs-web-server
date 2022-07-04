import typing

from alws.models import User
from alws.perms.actions import ActionsMaskMapping


def can_perform(obj: typing.Any, user: User, action: str) -> bool:
    if action not in ActionsMaskMapping:
        raise ValueError(f'Cannot detect if user can perform action: '
                         f'{action} is missing in mapping')

    # FIXME: Enable after migration to fastapi-users
    # if user.superuser:
    #     return True

    action_mask = ActionsMaskMapping[action]

    # Need to find intersection between user and object groups
    if not hasattr(obj, 'roles') and not hasattr(obj, 'team'):
        raise ValueError('Cannot detect object roles')
    obj_roles = []
    if hasattr(obj, 'roles'):
        obj_roles.extend(obj.roles)
    if hasattr(obj, 'team'):
        obj_roles.extend(obj.team.roles)

    groups_intersection = list(set(user.roles) & set(obj_roles))
    object_permissions = obj.permissions_triad
    if obj.owner.id == user.id:
        is_performable = bool(object_permissions.owner & action_mask)
    else:
        if groups_intersection:
            is_performable = bool(object_permissions.group & action_mask)
        else:
            is_performable = bool(object_permissions.other & action_mask)

    if not is_performable:
        return False

    is_allowed = False
    for group in groups_intersection:
        action_names = {act.name for act in group.actions}
        is_allowed = action in action_names
        if is_allowed:
            break

    return is_allowed
