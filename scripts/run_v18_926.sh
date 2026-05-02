#!/bin/bash
# v1.8 9:26 推送 cron
# 触发: 北京 09:26 (= 美西 PDT 18:26 / PST 17:26)
cd /Users/openclaw/.openclaw/workspace-dengxian
exec /usr/bin/python3 scripts/reversal_v18_push_926.py 2>&1
