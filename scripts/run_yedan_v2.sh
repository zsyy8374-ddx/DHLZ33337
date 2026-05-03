#!/bin/bash
# 战法 B v2 (软封+早封 T+1) 推送
# 周一-周五 北京 15:05 收盘后跑
set -e
cd /Users/openclaw/.openclaw/workspace-dengxian

today=$(TZ=Asia/Shanghai date +%Y%m%d)
log_dir=picks/yedan_v2
mkdir -p "$log_dir"
log_file="$log_dir/${today}.log"

echo "=== 战法 B v2 推送 $today ===" | tee "$log_file"

# 跑选股
python3 scripts/yedan_push_v2.py --date "$today" 2>&1 | tee -a "$log_file"

picks_file="data/wencai/yedan_v2_picks_${today}.txt"
if [ ! -f "$picks_file" ]; then
    echo "无候选文件" | tee -a "$log_file"
    exit 2
fi

# 检查内容是否有真信号 (软封+早封 档非空)
if grep -q "无$" "$picks_file"; then
    if grep -A1 "软封+早封" "$picks_file" | grep -q "  无$"; then
        echo "软封+早封档为空, 跳过推送" | tee -a "$log_file"
        exit 2
    fi
fi

# 推送到微信会话
msg_body=$(cat "$picks_file")
echo "[微信推送]" | tee -a "$log_file"

# qq-send.js 同时邮件留底
node /Users/openclaw/.openclaw/workspace-dengxian/qq-send.js \
    --to 1628354330@qq.com \
    --subject "战法B v2 ${today} 软封+早封" \
    --body "$msg_body" \
    2>&1 | tee -a "$log_file"

echo "=== 完成 ===" | tee -a "$log_file"
exit 0
