import logging


__all__ = ['setup_logging']


def setup_logging(verbose: bool = False):
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s',
                        level=log_level, datefmt='%Y-%m-%d %H:%M:%S')
