import sentry_sdk
from pika.exceptions import StreamLostError

from alws.config import settings


def sentry_init():
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        traces_sample_rate=settings.sentry_traces_sample_rate,
        environment=settings.sentry_environment,
        ignore_errors=[
            ConnectionResetError,
            StreamLostError,
        ],
    )
