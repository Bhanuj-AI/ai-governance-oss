#!/bin/sh
set -eu

exec uv run python scripts/replay/smoke_replay.py
