#!/bin/bash
# 战法 B v2 D+1 实盘命中追踪
# 周一-周五 北京 9:35 跑 (开盘 5 分钟后, D+1 开盘价就有了)
set -e
cd /Users/openclaw/.openclaw/workspace-dengxian

today=$(TZ=Asia/Shanghai date +%Y%m%d)
log_dir=picks/yedan_v2
mkdir -p "$log_dir"
log_file="$log_dir/track_${today}.log"

echo "=== 战法 B v2 命中追踪 $today (D+1) ===" | tee "$log_file"

# 1. 检查今天是不是交易日 (D+1 必须开盘)
weekday=$(TZ=Asia/Shanghai date +%u)
if [ "$weekday" -ge 6 ]; then
    echo "周末 不交易, 跳过" | tee -a "$log_file"; exit 2
fi

case "$today" in
    20260101|20260202|20260203|20260204|20260205|20260206|20260207|20260208|20260209|20260210|20260211|20260212|20260213|20260214|20260215|20260216|20260217)
        echo "春节休市 $today" | tee -a "$log_file"; exit 2 ;;
    20260403|20260404|20260405|20260406)
        echo "清明休市 $today" | tee -a "$log_file"; exit 2 ;;
    20260501|20260504|20260505)
        echo "五一休市 $today" | tee -a "$log_file"; exit 2 ;;
    20260622|20260623|20260624)
        echo "端午休市 $today" | tee -a "$log_file"; exit 2 ;;
    20260928|20260929|20260930|20261001|20261002|20261003|20261004|20261005|20261006|20261007)
        echo "中秋+国庆休市 $today" | tee -a "$log_file"; exit 2 ;;
esac

# 2. 跑追踪 (默认: 找最近 picks 文件作为 D, today 作为 D+1)
python3 scripts/yedan_v2_track.py --d1 "$today" 2>&1 | tee -a "$log_file"

# 3. 微信推送命中结果
last_picks=$(ls -t data/wencai/yedan_v2_picks_*.txt 2>/dev/null | head -1)
if [ -z "$last_picks" ]; then
    echo "无 picks 文件, 不发推送" | tee -a "$log_file"; exit 2
fi
d=$(basename "$last_picks" | sed 's/yedan_v2_picks_//;s/.txt//')

# 跳过同日 (没有 D+1 关系)
if [ "$d" = "$today" ]; then
    echo "今天既是 D 又是 D+1? 异常, 跳过" | tee -a "$log_file"; exit 2
fi

# 输出追踪报告 (取脚本主要输出)
report=$(grep -A 100 "$d → $today" "$log_file" 2>/dev/null | head -50)
if [ -n "$report" ]; then
    echo "[追踪报告]" | tee -a "$log_file"
    node /Users/openclaw/.openclaw/workspace-dengxian/qq-send.js \
        --to 1628354330@qq.com \
        --subject "战法B v2 命中追踪 $d → $today" \
        --body "$report" 2>&1 | tee -a "$log_file"
fi

echo "=== 完成 ===" | tee -a "$log_file"
exit 0
