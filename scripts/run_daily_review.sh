#!/bin/bash
# 每日盘后复盘 — 北京 16:00 跑 (= 美西 PDT 01:00 / PST 00:00)
cd /Users/openclaw/.openclaw/workspace-dengxian
exec /usr/bin/python3 -u scripts/v18_v19_daily_review.py 2>&1
