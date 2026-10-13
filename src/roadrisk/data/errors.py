"""Errors raised by the data layer."""


class DataError(Exception):
    """Base class for catalog, file, and schema failures."""


class ManifestError(DataError):
    """The manifest is missing a field or contains an invalid value."""


class DataFileError(DataError):
    """A required file is missing, empty, or unreadable."""


class IntegrityError(DataError):
    """File size or SHA-256 does not match the manifest."""


class SchemaError(DataError):
    """A table header does not satisfy the collision contract."""


class FeatureLeakageError(SchemaError):
    """A feature list includes the label or a post-event column."""


class FeatureContractError(DataError):
    """The feature specification or temporal split policy is inconsistent."""
