"""Initialize PostgreSQL schemas before Kavach application processes start."""

from __future__ import annotations

import os

from .database import PostgresDatabase


def migration_dsns_from_environment() -> tuple[str, ...]:
    """Read pipe-delimited PostgreSQL DSNs for the deployment migration job."""
    value = os.getenv("KAVACH_POSTGRES_MIGRATION_DSNS", "")
    dsns = tuple(item.strip() for item in value.split("|") if item.strip())
    if not dsns:
        raise ValueError("KAVACH_POSTGRES_MIGRATION_DSNS must contain at least one DSN")
    return dsns


def main() -> None:
    """Apply idempotent schema initialization to each owned PostgreSQL database."""
    for dsn in migration_dsns_from_environment():
        PostgresDatabase(dsn).initialize()


if __name__ == "__main__":
    main()
