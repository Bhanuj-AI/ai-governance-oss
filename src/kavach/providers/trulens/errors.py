class TruLensProviderError(Exception):
    """
    Base error raised by the TruLens evaluation adapter.
    """


class UnsupportedTruLensMetricError(TruLensProviderError):
    """
    Raised when a Kavach metric cannot be mapped to TruLens.
    """
