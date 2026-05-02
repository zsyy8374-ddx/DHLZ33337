#!/bin/bash
# v1.9 9:35 推送 cron
# 触发: 北京 09:36 (= 美西 PDT 18:36 / PST 17:36)
cd /Users/openclaw/.openclaw/workspace-dengxian
exec /usr/bin/python3 scripts/reversal_v19_push_935.py 2>&1
