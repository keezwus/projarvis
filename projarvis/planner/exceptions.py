class SchedulingError(Exception):
    """Base exception for all projarvis L2 errors."""


class ValidationError(SchedulingError):
    """Parameter validation failure."""


class TimeMappingError(SchedulingError):
    """ISO 8601 string does not fall within available time."""


class ConstraintError(SchedulingError):
    """Constraint handling failure: unknown type, invalid params."""
