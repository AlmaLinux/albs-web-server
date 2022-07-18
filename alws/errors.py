class BuildError(Exception):
    pass


class EmptyBuildError(Exception):
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


class ReleaseLogicError(Exception):
    pass


class BuildAlreadySignedError(ValueError):
    pass


class ArtifactConversionError(Exception):
    pass


class ArtifactChecksumError(Exception):
    pass


class SrpmProvisionError(Exception):
    pass


class MultilibProcessingError(Exception):
    pass


class NoarchProcessingError(Exception):
    pass


class ModuleUpdateError(Exception):
    pass


class RepositoryAddError(Exception):
    pass


class PermissionDenied(Exception):
    pass
