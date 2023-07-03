import logging
import typing

from alws.models import User
from alws.perms.actions import ActionsMaskMapping


def can_perform(obj: typing.Any, user: User, action: str) -> bool:
    if action not in ActionsMaskMapping:
        raise ValueError(f'Cannot detect if user can perform action: '
                         f'{action} is missing in mapping')

    if user.is_superuser or obj.owner.id == user.id:
        return True

    action_mask = ActionsMaskMapping[action]

    # Need to find intersection between user and object groups
    if not hasattr(obj, 'roles') and not hasattr(obj, 'team'):
        raise ValueError('Cannot detect object roles')
    obj_roles = []
    if hasattr(obj, 'roles'):
        obj_roles.extend(obj.roles)
    if hasattr(obj, 'team'):
        obj_roles.extend(obj.team.roles)

    logging.debug('Object roles: %s', str(obj_roles))
    logging.debug('User roles: %s', str(user.roles))

    groups_intersection = list(set(user.roles) & set(obj_roles))
    logging.debug('Intersection between object and user roles: %s',
                  str(groups_intersection))
    object_permissions = obj.permissions_triad
    is_performable = bool(object_permissions.other & action_mask)
    if groups_intersection:
        is_performable = bool(object_permissions.group & action_mask)

    if not is_performable:
        return False

    is_allowed = False
    for group in groups_intersection:
        action_names = {act.name for act in group.actions}
        logging.debug('Action names for group %s: %s',
                      group.name, str(action_names))
        is_allowed = action in action_names
        if is_allowed:
            break

    return is_allowed
