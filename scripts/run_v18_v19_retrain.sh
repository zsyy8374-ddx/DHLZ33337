#!/bin/bash
# v1.8 + v1.9 周日 retrain
# 触发: 周日 北京 22:00 (= 美西 PDT 周日 7:00 / PST 6:00)
cd /Users/openclaw/.openclaw/workspace-dengxian
exec /usr/bin/python3 -u scripts/v18_v19_retrain_weekly.py 2>&1
