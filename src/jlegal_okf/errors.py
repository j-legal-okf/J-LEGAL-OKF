"""Stable exception types for the public J-LEGAL-OKF core."""


class JLegalError(Exception):
    """Base error for deterministic public-core operations."""


class AdapterError(JLegalError):
    """An input adapter cannot preserve the supplied source safely."""


class ValidationError(JLegalError):
    """Canonical corpus or artifact validation failed."""

    def __init__(self, message: str, diagnostics=()) -> None:
        super().__init__(message)
        self.diagnostics = tuple(diagnostics)
