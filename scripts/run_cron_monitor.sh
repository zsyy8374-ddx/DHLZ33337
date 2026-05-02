#!/bin/bash
# Cron 错误监控
cd /Users/openclaw/.openclaw/workspace-dengxian
exec /usr/bin/python3 -u scripts/cron_error_monitor.py 2>&1
