"""Application-layer error types and domain error mapper."""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError

from mind.app.contracts import AppError, AppErrorCode

# ---------------------------------------------------------------------------
# Exception hierarchy
# ---------------------------------------------------------------------------


class AppServiceError(RuntimeError):
    """Base exception for application service layer errors."""

    def __init__(self, message: str, code: AppErrorCode = AppErrorCode.INTERNAL_ERROR) -> None:
        super().__init__(message)
        self.code = code


class NotFoundError(AppServiceError):
    """Raised when a requested resource does not exist."""

    def __init__(self, message: str = "resource not found") -> None:
        super().__init__(message, code=AppErrorCode.NOT_FOUND)


class AuthorizationError(AppServiceError):
    """Raised when the caller lacks required permissions."""

    def __init__(self, message: str = "unauthorized") -> None:
        super().__init__(message, code=AppErrorCode.AUTHORIZATION_ERROR)


class ValidationError(AppServiceError):
    """Raised when input validation fails."""

    def __init__(self, message: str = "validation failed") -> None:
        super().__init__(message, code=AppErrorCode.VALIDATION_ERROR)


class ConflictError(AppServiceError):
    """Raised on idempotency or conflict violations."""

    def __init__(self, message: str = "conflict") -> None:
        super().__init__(message, code=AppErrorCode.CONFLICT)


# ---------------------------------------------------------------------------
# Domain error mapper
# ---------------------------------------------------------------------------


def map_domain_error(exc: Exception) -> AppError:
    """Map a domain exception to a unified ``AppError`` payload.

    Handles ``StoreError``, ``GovernanceServiceError``,
    ``AccessServiceError``, ``OfflineMaintenanceError``,
    Pydantic ``ValidationError``, and generic ``AppServiceError``.
    """

    from mind.kernel.store import StoreError

    # StoreError
    if isinstance(exc, StoreError):
        return AppError(
            code=AppErrorCode.STORE_ERROR,
            message=str(exc),
            retryable=False,
        )

    # GovernanceServiceError
    try:
        from mind.governance.service import GovernanceServiceError

        if isinstance(exc, GovernanceServiceError):
            return AppError(
                code=AppErrorCode.GOVERNANCE_EXECUTION_FAILED,
                message=str(exc),
                retryable=False,
            )
    except ImportError:
        pass

    # AccessServiceError
    try:
        from mind.access.service import AccessServiceError

        if isinstance(exc, AccessServiceError):
            return AppError(
                code=AppErrorCode.ACCESS_SERVICE_ERROR,
                message=str(exc),
                retryable=False,
            )
    except ImportError:
        pass

    # OfflineMaintenanceError
    try:
        from mind.offline.service import OfflineMaintenanceError

        if isinstance(exc, OfflineMaintenanceError):
            return AppError(
                code=AppErrorCode.OFFLINE_MAINTENANCE_ERROR,
                message=str(exc),
                retryable=False,
            )
    except ImportError:
        pass

    # Pydantic ValidationError
    if isinstance(exc, PydanticValidationError):
        return AppError(
            code=AppErrorCode.VALIDATION_ERROR,
            message=str(exc),
            retryable=False,
            details={"errors": exc.errors()},
        )

    # AppServiceError (our own hierarchy)
    if isinstance(exc, AppServiceError):
        return AppError(
            code=exc.code,
            message=str(exc),
            retryable=False,
        )

    # Fallback
    return AppError(
        code=AppErrorCode.INTERNAL_ERROR,
        message=str(exc),
        retryable=False,
    )


def map_primitive_error(error: object) -> AppError:
    """Map a primitive-layer error payload to the unified app envelope."""

    from mind.primitives.contracts import PrimitiveError

    if not isinstance(error, PrimitiveError):
        return AppError(
            code=AppErrorCode.INTERNAL_ERROR,
            message=str(error),
            retryable=False,
        )

    try:
        code = AppErrorCode(error.code.value)
    except ValueError:
        code = AppErrorCode.INTERNAL_ERROR

    return AppError(
        code=code,
        message=error.message,
        retryable=error.retryable,
        details=dict(error.details),
    )
