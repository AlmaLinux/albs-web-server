from .permissions import handlers as perm_handlers
from .products import handlers as product_handlers
from .uploads import handlers as upload_handlers


__all__ = ['handlers']


add_handlers = (
    perm_handlers,
    product_handlers,
    upload_handlers,
)
handlers = {}
for add_handler in add_handlers:
    for key, value in add_handler.items():
        handlers[key] = value
