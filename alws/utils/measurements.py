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
