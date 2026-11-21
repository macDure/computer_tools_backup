#!/bin/sh
# Keep the historical entry point on the same recovery and checking path.
set -eu
BASE=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
case "${1:-}" in
    https://111.202.232.70:1443/|https://111.202.232.70:1443) shift ;;
esac
exec "$BASE/connect-trustaccess.sh" "$@"
