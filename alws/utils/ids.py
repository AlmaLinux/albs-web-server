import random
import time


__all__ = ['get_random_unique_version']


def get_random_unique_version():
    return int(str(int(time.time())) + str(random.randint(1000000, 9999999)))
