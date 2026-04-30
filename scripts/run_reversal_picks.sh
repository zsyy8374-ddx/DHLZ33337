#!/bin/bash
# REVERSAL DAILY: 用 v0.3 模型推每日回马枪候选
# Exit code: 0=已推送, 1=数据缺失, 2=无候选
cd /Users/openclaw/.openclaw/workspace-dengxian
exec python3 -u scripts/reversal_picks_v3.py 2>&1
