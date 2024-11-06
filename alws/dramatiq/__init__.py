"""
Dramatiq new tasks how-to:
    1. ALWAYS set max_retries to some value, since by default
       max_retries is infinity. That's probably not what you want by default
    2. If you wrote a new function tasks, you should import it here,
       dramatiq knows only about tasks imported in this __init__.py
    3. Try to think about task priority a bit. Default value is 0 (very high),
       and it's important for all tasks which involves user interaction
       to have priority 0.
    4. If you need to use async function in your dramatiq task - ALWAYS use
       loop from this __init__.py, since creating multiple loops for tasks
       will break your tasks.
"""

import asyncio

import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker

from alws.config import settings

rabbitmq_broker = RabbitmqBroker(
    url=f"amqp://"
    f"{settings.rabbitmq_default_user}:"
    f"{settings.rabbitmq_default_pass}@"
    f"{settings.rabbitmq_default_host}:5672/"
    f"{settings.rabbitmq_default_vhost}",
)
dramatiq.set_broker(rabbitmq_broker)
event_loop = asyncio.get_event_loop()

# Tasks import started from here
from alws.dramatiq.build import build_done, start_build
from alws.dramatiq.errata import (
    bulk_errata_release,
    bulk_new_errata_release,
    create_new_errata,
    release_errata,
    release_new_errata,
    reset_records_threshold,
)

# dramatiq.user and dramatiq.products need to go before dramatiq.releases
from alws.dramatiq.products import perform_product_modification
from alws.dramatiq.releases import execute_release_plan, revert_release
from alws.dramatiq.sign_task import complete_sign_task
from alws.dramatiq.tests import complete_test_task
from alws.dramatiq.user import perform_user_removal
