#!/bin/bash
# 韭研公社雷达引擎 wrapper
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$DIR/env.sh" >/dev/null 2>&1
exec python3 "$DIR/jiuyan_radar.py" "$@"
