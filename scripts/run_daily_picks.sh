#!/bin/bash
# 包装脚本: 直接调用 daily_picks.py, 输出全部到 stdout 让 cron 抓走
exec python3 /Users/openclaw/.openclaw/workspace-dengxian/scripts/daily_picks.py "$@"
