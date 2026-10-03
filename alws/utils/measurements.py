import time
from datetime import datetime
from functools import wraps

from alws.utils.task_metrics import observe_stage


def class_measure_work_time_async(stats_key_name: str):
    """Record the call in ``self.stats`` and as an ``albs_task_stage_seconds``
    stage named ``stats_key_name``."""

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            start = datetime.utcnow()
            perf_start = time.perf_counter()
            self, *args = args
            try:
                result = await fn(self, *args, **kwargs)
            finally:
                observe_stage(stats_key_name, time.perf_counter() - perf_start)
            finish = datetime.utcnow()
            self.stats[stats_key_name] = {
                "start_ts": start.isoformat(),
                "finish_ts": finish.isoformat(),
                "delta_ts": (finish - start).total_seconds(),
            }
            return result

        return wrapper

    return decorator
