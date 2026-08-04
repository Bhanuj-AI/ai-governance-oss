"""Errors used by the route contribution API."""


class RouteConflictError(RuntimeError):
    """Raised when a route is duplicated or replacement lacks OSS approval."""
