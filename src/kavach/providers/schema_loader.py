"""Load provider-contributed configuration schema resources."""

from __future__ import annotations

import json
from collections.abc import Mapping
from importlib.resources import files
from typing import Any

from kavach.providers.provider_descriptor import normalize_provider_name


def load_provider_configuration_schema(provider_type: str) -> Mapping[str, Any]:
    """Load the versioned schema resource owned by one shipped adapter."""
    name = normalize_provider_name(provider_type)
    resource = files("kavach.providers.schemas").joinpath(f"{name}.json")
    return json.loads(resource.read_text(encoding="utf-8"))
