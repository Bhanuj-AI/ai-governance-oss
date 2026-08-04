"""Common, explicit context passed across Kavach extension boundaries.

Extension contracts use a lightweight mapping instead of importing the
tenancy implementation. This keeps the public SPI package stable and prevents
plugins from coupling to internal persistence or authentication classes.
"""

from __future__ import annotations

from collections.abc import Mapping

# Extensions must receive tenancy from their caller; they must not infer it
# from process-wide state or environment configuration. Required keys remain
# contract-specific; common examples are ``organization_id`` and ``project_id``.
TenantContext = Mapping[str, str]
