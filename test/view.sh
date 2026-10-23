#!/bin/sh
# Browse test/out results
exec python3 "$(dirname "$0")/view.py" "$@"
