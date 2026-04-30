#!/bin/bash
# REVERSAL 实战追踪 (cron 调用)
# 北京时间 18:35 收盘后跑

cd /Users/openclaw/.openclaw/workspace-dengxian || exit 1

# 评估今天 (北京时间)
TODAY=$(TZ=Asia/Shanghai date +%Y-%m-%d)
LOG=/tmp/reversal_track_${TODAY}.log

echo "=== REVERSAL track $TODAY ===" > "$LOG"
date '+%F %T %Z' >> "$LOG"
echo "" >> "$LOG"

python3 scripts/reversal_track_full.py "$TODAY" 2>&1 | tee -a "$LOG"

echo "" >> "$LOG"
echo "=== Done ===" >> "$LOG"

# 把摘要发到微信 (主体由 cron 自己处理 announce)
tail -40 "$LOG"
