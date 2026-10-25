class EVChargeOptException(Exception):
    """Base exception for EVCharge-Opt."""
    def __init__(self, message: str, status_code: int = 400, details: dict = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details or {}


class EntityNotFoundError(EVChargeOptException):
    def __init__(self, entity_name: str, entity_id: str):
        super().__init__(
            message=f"{entity_name} with identifier '{entity_id}' not found.",
            status_code=404,
            details={"entity_name": entity_name, "entity_id": entity_id},
        )


class ConstraintViolationError(EVChargeOptException):
    def __init__(self, message: str, violations: list = None):
        super().__init__(
            message=message,
            status_code=422,
            details={"violations": violations or []},
        )


class InvalidForecastError(EVChargeOptException):
    def __init__(self, message: str, validation_errors: list = None):
        super().__init__(
            message=message,
            status_code=422,
            details={"validation_errors": validation_errors or []},
        )


class ProviderIntegrationError(EVChargeOptException):
    def __init__(self, message: str, is_retryable: bool = False, raw_response: str = None):
        super().__init__(
            message=message,
            status_code=502,
            details={"is_retryable": is_retryable, "raw_response": raw_response},
        )
        self.is_retryable = is_retryable


class IdempotencyConflictError(EVChargeOptException):
    def __init__(self, message: str, idempotency_key: str):
        super().__init__(
            message=message,
            status_code=409,
            details={"idempotency_key": idempotency_key},
        )


class StationMappingError(EVChargeOptException):
    def __init__(self, message: str, station_id: str = None):
        super().__init__(
            message=message,
            status_code=422,
            details={"station_id": station_id} if station_id else {},
        )
