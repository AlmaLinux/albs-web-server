from .builds import handlers as build_handlers
from .not_found import handlers as not_found_handler
from .permissions import handlers as perm_handlers
from .products import handlers as product_handlers
from .sign_task import handlers as sign_task_handlers
from .uploads import handlers as upload_handlers

__all__ = ['handlers']


add_handlers = (
    build_handlers,
    not_found_handler,
    perm_handlers,
    product_handlers,
    sign_task_handlers,
    upload_handlers,
)
handlers = {}
for add_handler in add_handlers:
    for key, value in add_handler.items():
        handlers[key] = value
