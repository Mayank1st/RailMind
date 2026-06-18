"""Provider-layer failures — caught and translated to RailMindException by the
domain service (app/services/live_status_service.py)."""


class ProviderError(Exception):
    """Base for all provider failures."""


class ProviderTimeoutError(ProviderError):
    pass


class ProviderQuotaExceededError(ProviderError):
    pass


class ProviderInvalidTrainError(ProviderError):
    pass


class ProviderTrainNotRunningError(ProviderError):
    pass


class ProviderInvalidResponseError(ProviderError):
    pass
