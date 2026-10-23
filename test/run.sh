#!/bin/sh
# Run the black-box TUI tests (deps via uvx)
exec uvx --with pyte python "$(dirname "$0")/tui.py" "$@"
