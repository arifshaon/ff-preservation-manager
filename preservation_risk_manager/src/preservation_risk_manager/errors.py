class PreservationRiskManagerError(Exception):
    """Base exception for preservation-risk-manager failures."""


class FrameworkError(PreservationRiskManagerError):
    """Raised when a framework or posture configuration is invalid."""


class PolicyConfigurationError(PreservationRiskManagerError):
    """Raised when action policy configuration is contradictory."""
