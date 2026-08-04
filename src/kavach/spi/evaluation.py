"""Supported evaluation-provider extension contract.

This public re-export promotes the existing evaluation adapter contract to the
open-core SPI surface. New providers should import it from this module rather
than from the legacy implementation package, preserving the right to relocate
the implementation without breaking an enterprise extension.
"""

from kavach.providers.evaluation_provider import EvaluationProvider

__all__ = ["EvaluationProvider"]
