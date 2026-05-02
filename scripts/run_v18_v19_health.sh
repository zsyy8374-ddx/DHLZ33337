#!/bin/bash
# v1.8/v1.9 系统自检 — 节后 5-6 周三 9:00 北京 跑
cd /Users/openclaw/.openclaw/workspace-dengxian
exec /usr/bin/python3 -u scripts/v18_v19_health_check.py 2>&1
