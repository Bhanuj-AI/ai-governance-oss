#!/usr/bin/env bash
# Compatibility wrapper. New launchers discover all service identities.
exec "$(cd "$(dirname "$0")" && pwd)/get-service-account-actorids.sh"
