from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from psycopg.types.json import Jsonb


def with_jsonb_fields(
    record: Mapping[str, Any],
    *field_names: str,
) -> dict[str, Any]:
    adapted = dict(record)

    for field_name in field_names:
        value = adapted[field_name]
        adapted[field_name] = (
            Jsonb(json.loads(value))
            if value is not None
            else None
        )

    return adapted
