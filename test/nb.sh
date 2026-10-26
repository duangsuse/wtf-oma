#!/bin/sh
# Run the CDP tests over v2/demo.ipynb (deps via uvx)
exec uvx --with pyte python "$(dirname "$0")/nb.py" "$@"
