from .permissions import handlers as perm_handlers
from .products import handlers as product_handlers


__all__ = ['handlers']


handlers = {}
for add_handler in (perm_handlers, product_handlers):
    for key, value in add_handler.items():
        handlers[key] = value
