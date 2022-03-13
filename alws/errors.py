class BuildError(Exception):
    pass


class SignError(Exception):
    pass


class AlreadyBuiltError(Exception):
    pass


class DataNotFoundError(Exception):
    pass


class DistributionError(Exception):
    pass


class EmptyReleasePlan(ValueError):
    pass


class MissingRepository(ValueError):
    pass


class SignKeyAlreadyExistsError(ValueError):
    pass


class BuildAlreadySignedError(ValueError):
    pass
