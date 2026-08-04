"""Kavach package version resolved from project metadata."""

from importlib.metadata import PackageNotFoundError, version


def _resolve_version() -> str:
    try:
        return version("kavach")
    except PackageNotFoundError:
        # Source archives or direct source-tree execution may not have package
        # metadata installed. Keep imports usable without inventing a release.
        return "0.0.0+unknown"


__version__ = _resolve_version()

