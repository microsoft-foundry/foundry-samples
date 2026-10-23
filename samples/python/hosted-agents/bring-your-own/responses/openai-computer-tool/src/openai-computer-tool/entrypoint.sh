#!/bin/sh
set -eu

export DISPLAY="${DISPLAY:-:99}"

if ! pgrep -x Xvfb >/dev/null 2>&1; then
    Xvfb "$DISPLAY" -screen 0 1280x800x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
    sleep 1
fi

touch "$HOME/.Xauthority"

exec /app/user_agent/.venv/bin/python /app/user_agent/main.py "$@"
