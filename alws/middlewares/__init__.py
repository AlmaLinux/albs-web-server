from .permissions import handlers as perm_handlers
from .products import handlers as product_handlers
from .uploads import handlers as upload_handlers
from .not_found import handlers as not_found_handler
from .sign_task import handlers as sign_task_handlers


__all__ = ['handlers']


add_handlers = (
    perm_handlers,
    product_handlers,
    upload_handlers,
    not_found_handler,
    sign_task_handlers,
)
handlers = {}
for add_handler in add_handlers:
    for key, value in add_handler.items():
        handlers[key] = value
