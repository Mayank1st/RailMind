class RailMindException(Exception):
    error_code: str = "RM-GEN-000"
    message: str = "Something went wrong"
    status_code: int = 500

    def __init__(
        self,
        code: str | None = None,
        message: str | None = None,
        status_code: int | None = None,
    ):
        self.code = code or self.error_code
        self.message = message or self.__class__.message
        self.status_code = status_code or self.__class__.status_code
        super().__init__(self.message)


# ─────────────────────────── AUTH ───────────────────────────


class InvalidCredentialsError(RailMindException):
    error_code = "RM-AUTH-001"
    status_code = 401
    message = "Invalid email/username or password"


class TokenExpiredError(RailMindException):
    error_code = "RM-AUTH-002"
    status_code = 401
    message = "Token has expired"


class OTPVerificationError(RailMindException):
    error_code = "RM-AUTH-003"
    status_code = 400
    message = "OTP verification failed"


class GoogleTokenInvalidError(RailMindException):
    error_code = "RM-AUTH-017"
    status_code = 401
    message = "Google ID token is invalid or expired"


class ProviderMismatchError(RailMindException):
    error_code = "RM-AUTH-018"
    status_code = 409
    message = "This account uses Google Sign-In. Please continue with Google."


class GoogleEmailUnverifiedError(RailMindException):
    error_code = "RM-AUTH-010"
    status_code = 403
    message = "Google account email is not verified"


# ─────────────────────────── BOOKING ───────────────────────────


class SeatNotAvailableError(RailMindException):
    error_code = "RM-BKG-001"
    status_code = 409
    message = "Seat not available in the selected class"


class MaxPassengersExceededError(RailMindException):
    error_code = "RM-BKG-002"
    status_code = 422
    message = "Maximum passengers per booking exceeded"


class BookingWindowClosedError(RailMindException):
    error_code = "RM-BKG-003"
    status_code = 403
    message = "Booking window is closed for this journey"


class DuplicateBookingError(RailMindException):
    error_code = "RM-BKG-004"
    status_code = 409
    message = "Duplicate booking detected"


# ─────────────────────────── TRAIN ───────────────────────────


class TrainNotFoundError(RailMindException):
    error_code = "RM-TRN-001"
    status_code = 404
    message = "Train not found"


class InvalidStationCodeError(RailMindException):
    error_code = "RM-TRN-002"
    status_code = 400
    message = "Invalid station code"


# ─────────────────────────── WAITLIST ───────────────────────────


class WaitlistFullError(RailMindException):
    error_code = "RM-WL-001"
    status_code = 409
    message = "Waitlist is full for this train/class"


# ─────────────────────────── RATE LIMIT ───────────────────────────


class RateLimitExceededError(RailMindException):
    error_code = "RM-RATE-001"
    status_code = 429
    message = "Too many requests. Please try again later."


# ─────────────────────────── DATABASE ───────────────────────────


class DatabaseError(RailMindException):

    error_code = "RM-DB-001"
    status_code = 503
    message = "A database error occurred. Please try again later."


# ─────────────────────────── LIVE STATUS ───────────────────────────


class LiveStatusUnavailableError(RailMindException):
    error_code = "RM-LIVE-001"
    status_code = 503
    message = "Live tracking temporarily unavailable. Try again shortly."


class LiveTrainNotFoundError(RailMindException):
    error_code = "RM-LIVE-002"
    status_code = 404
    message = "Train number not found"


class LiveTrainNotRunningError(RailMindException):
    error_code = "RM-LIVE-003"
    status_code = 422
    message = "Train does not run on this date"


# ─────────────────────────── CHART PREPARATION ───────────────────────────
# Background-only (Celery); never surfaced over HTTP, but kept in the RM code
# scheme for consistent logging.


class ChartAlreadyPreparedError(RailMindException):
    error_code = "RM-CHART-001"
    status_code = 409
    message = "Chart already prepared for this stage"


class ChartInventoryNotFoundError(RailMindException):
    error_code = "RM-CHART-002"
    status_code = 404
    message = "No seat inventory found for chart preparation"


class ChartCascadeError(RailMindException):
    error_code = "RM-CHART-003"
    status_code = 500
    message = "Promotion cascade failed during chart preparation"
