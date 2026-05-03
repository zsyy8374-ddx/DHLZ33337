#!/bin/bash
# 每日 17:25 北京时间 (DAILY 推送前 5 分钟) 跑一次:
# 1. 拉今日涨停股 (问财)
# 2. 更新 sector_strength_<TODAY>.csv
# 3. 重算 8 日趋势 sector_trend_8day.csv

set -e
cd /Users/openclaw/.openclaw/workspace-dengxian

# 北京时间日期
BJ_DATE=$(TZ='Asia/Shanghai' date '+%Y-%m-%d')
echo "=== sector_update for $BJ_DATE (北京) ==="

# 1. 拉今日 sector_strength
python3 scripts/sector_strength.py "$BJ_DATE" 2>&1 | tail -10

# 2. 重算 8 日趋势 (向前数 8 个交易日)
# 简化: 直接用 sector_batch + sector_trend
python3 scripts/sector_batch.py 2>&1 | tail -3
python3 scripts/sector_trend.py 2>&1 | tail -10

echo "✓ sector update done"
