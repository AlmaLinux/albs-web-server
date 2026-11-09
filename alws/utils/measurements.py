import contextlib
from datetime import datetime
from functools import wraps


def class_measure_work_time_async(stats_key_name: str):
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            start = datetime.utcnow()
            self, *args = args
            result = await fn(self, *args, **kwargs)
            finish = datetime.utcnow()
            self.stats[stats_key_name] = {
                "start_ts": start.isoformat(),
                "finish_ts": finish.isoformat(),
                "delta_ts": (finish - start).total_seconds(),
            }
            return result

        return wrapper

    return decorator


def record_stage(stats: dict, stats_key_name: str, start: datetime):
    """
    Stores the time spent since `start` in `stats` in the same format as
    `class_measure_work_time_async` does.

    A stage that is recorded several times (e.g. a request made in a loop)
    is summed up: `delta_ts` is the total time spent in it, `start_ts` is
    when it ran first and `finish_ts` is when it ran last. Callers that
    reuse `stats` between runs should drop the key before the first one.
    """
    finish = datetime.utcnow()
    delta = (finish - start).total_seconds()
    previous = stats.get(stats_key_name)
    if previous:
        start = datetime.fromisoformat(previous["start_ts"])
        delta += previous["delta_ts"]
    stats[stats_key_name] = {
        "start_ts": start.isoformat(),
        "finish_ts": finish.isoformat(),
        "delta_ts": delta,
    }


@contextlib.contextmanager
def measure_stage(stats: dict, stats_key_name: str):
    """Context manager version of `record_stage`."""
    start = datetime.utcnow()
    try:
        yield
    finally:
        record_stage(stats, stats_key_name, start)
