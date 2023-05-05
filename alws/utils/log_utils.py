import logging
from alws.config import settings

__all__ = ['setup_logger']

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(settings.logging_level)

    return logger
