#!/usr/bin/env bash
# daily-recap.sh — A股每日盘后龙虎榜抓取 (东财公开 datacenter-web API)
# Usage:
#   ./daily-recap.sh                          # 抓最近交易日(北京时间)
#   ./daily-recap.sh 2026-04-28               # 指定日期
#   ./daily-recap.sh 2026-04-28 002902,603931 # 指定日期+关注个股
#
# 输出: 工作区 memory/recap-YYYY-MM-DD.md
# 时区: 全部按北京时间 (Asia/Shanghai)
# 数据源: datacenter-web.eastmoney.com (无需登录, 海外可达)
# ⚠️ 龙虎榜数据北京时间 17:00 后才完整

set -u

WORKSPACE="${WORKSPACE:-/Users/openclaw/.openclaw/workspace-dengxian}"
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/605.1.15"

# ─── 参数 ───
if [ $# -ge 1 ] && [ -n "$1" ]; then
  DATE="$1"
else
  DATE=$(TZ='Asia/Shanghai' date +%Y-%m-%d)
fi
WATCH_CODES="${2:-}"

OUT="$WORKSPACE/memory/recap-$DATE.md"
mkdir -p "$WORKSPACE/memory"

echo "📅 复盘日期 (北京时间): $DATE"
echo "📁 输出文件: $OUT"
[ -n "$WATCH_CODES" ] && echo "🎯 关注个股: $WATCH_CODES"
echo

# 检查依赖
for tool in jq curl python3; do
  command -v $tool >/dev/null 2>&1 || { echo "❌ 缺少 $tool"; exit 1; }
done

# ─── 工具函数 ───
fetch() {
  curl -s -A "$UA" --max-time 12 "$1" 2>/dev/null
}

# 市场前缀转换 (用 case 而不是 zsh 不支持的 ${,,})
mkt_prefix() {
  case "$1" in
    6*) echo "sh" ;;
    0*|3*) echo "sz" ;;
    8*|4*|9*) echo "bj" ;;
    *) echo "sh" ;;
  esac
}

# ─── 报告头 ───
{
  echo "# A股龙虎榜复盘 — $DATE (北京时间)"
  echo
  echo "_自动生成 by daily-recap.sh @ $(TZ='Asia/Shanghai' date '+%Y-%m-%d %H:%M:%S 北京时间')_"
  echo
} > "$OUT"

# ─── 1. 龙虎榜个股汇总 ───
echo "📋 [1/3] 抓当日龙虎榜全部个股 (机构净买入排序)..."
SUMMARY_URL="https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=NET_BS_AMT&sortTypes=-1&pageSize=100&pageNumber=1&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&filter=(TRADE_DATE%3E%3D%27$DATE%27)(TRADE_DATE%3C%3D%27$DATE%27)"
SUMMARY=$(fetch "$SUMMARY_URL")

if [ -n "$SUMMARY" ] && echo "$SUMMARY" | jq -e '.result.data' >/dev/null 2>&1; then
  COUNT=$(echo "$SUMMARY" | jq '.result.data | length')
  TOTAL=$(echo "$SUMMARY" | jq -r '.result.pages // 1')
  echo "  ✅ 当日龙虎榜 $COUNT 只 (共 $TOTAL 页)"
  {
    echo "## 1. 龙虎榜上榜个股 — TOP20 (按龙虎榜净额排序)"
    echo
    echo "_共 $COUNT 只 (本页) / $TOTAL 页_"
    echo
    echo "| 代码 | 名称 | 收盘 | 涨幅% | 龙虎净额(万) | 上榜原因 |"
    echo "|---|---|---:|---:|---:|---|"
    echo "$SUMMARY" | jq -r '
      .result.data[0:20][]? |
      [
        .SECURITY_CODE,
        .SECURITY_NAME_ABBR,
        (.CLOSE_PRICE|tostring),
        ((.CHANGE_RATE * 100 | floor / 100)|tostring),
        ((.NET_BS_AMT // 0) / 10000 | floor | tostring),
        ((.EXPLAIN // .EXPLANATION // "") | gsub("\\|"; "/"))
      ] | @tsv
    ' | awk -F'\t' '{ printf "| %s | %s | %s | %s | %s | %s |\n", $1,$2,$3,$4,$5,$6 }'
    echo
  } >> "$OUT"
else
  echo "  ❌ 龙虎榜抓取失败 (可能17:00前 / 非交易日 / API变更)"
  {
    echo "## 1. 龙虎榜上榜个股"
    echo
    echo "⚠️ 抓取失败. 可能原因:"
    echo "- 现在是北京时间 17:00 前, 数据未出齐"
    echo "- 当日是非交易日 (周末/节假日)"
    echo "- 东财 API 变更"
    echo
  } >> "$OUT"
fi

# ─── 2. 龙虎榜净卖出 TOP10 (避雷参考) ───
echo "📉 [2/3] 抓净卖出 TOP10..."
SELL_URL="https://datacenter-web.eastmoney.com/api/data/v1/get?sortColumns=NET_BS_AMT&sortTypes=1&pageSize=10&pageNumber=1&reportName=RPT_DAILYBILLBOARD_DETAILSNEW&columns=ALL&filter=(TRADE_DATE%3E%3D%27$DATE%27)(TRADE_DATE%3C%3D%27$DATE%27)"
SELL=$(fetch "$SELL_URL")

if [ -n "$SELL" ] && echo "$SELL" | jq -e '.result.data' >/dev/null 2>&1; then
  echo "  ✅ 净卖出 TOP10"
  {
    echo "## 2. 龙虎榜 — 净卖出 TOP10 (避雷参考)"
    echo
    echo "| 代码 | 名称 | 收盘 | 涨幅% | 净卖出(万) | 原因 |"
    echo "|---|---|---:|---:|---:|---|"
    echo "$SELL" | jq -r '
      .result.data[0:10][]? |
      [
        .SECURITY_CODE,
        .SECURITY_NAME_ABBR,
        (.CLOSE_PRICE|tostring),
        ((.CHANGE_RATE * 100 | floor / 100)|tostring),
        ((.NET_BS_AMT // 0) / 10000 | floor | tostring),
        ((.EXPLAIN // .EXPLANATION // "") | gsub("\\|"; "/"))
      ] | @tsv
    ' | awk -F'\t' '{ printf "| %s | %s | %s | %s | %s | %s |\n", $1,$2,$3,$4,$5,$6 }'
    echo
  } >> "$OUT"
fi

# ─── 3. 关注个股 — 龙虎榜营业部明细 ───
if [ -n "$WATCH_CODES" ]; then
  echo "🎯 [3/3] 抓关注个股龙虎榜明细..."
  {
    echo "## 3. 关注个股 — 龙虎榜营业部明细"
    echo
  } >> "$OUT"

  IFS=',' read -ra CODES <<< "$WATCH_CODES"
  for CODE in "${CODES[@]}"; do
    CODE=$(echo "$CODE" | tr -d ' ')
    [ -z "$CODE" ] && continue
    PFX=$(mkt_prefix "$CODE")

    {
      echo "### $CODE"
      echo
      echo "**外链**:"
      echo "- 东财龙虎榜: https://data.eastmoney.com/stock/lhb,$DATE,$CODE.html"
      echo "- 复盘网: https://$CODE.fupanwang.com/longhu/$DATE.html"
      echo "- K线: https://quote.eastmoney.com/${PFX}${CODE}.html"
      echo
    } >> "$OUT"

    # 买方席位 (按净买额排序, 取 TOP10)
    BUY_URL="https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_BILLBOARD_DAILYDETAILSBUY&columns=ALL&filter=(SECURITY_CODE%3D%22$CODE%22)(TRADE_DATE%3E%3D%27$DATE%27)(TRADE_DATE%3C%3D%27$DATE%27)&pageNumber=1&pageSize=15&sortColumns=NET&sortTypes=-1"
    BUY=$(fetch "$BUY_URL")

    if [ -n "$BUY" ] && echo "$BUY" | jq -e '.result.data' >/dev/null 2>&1; then
      BUY_CNT=$(echo "$BUY" | jq '.result.data | length')
      if [ "$BUY_CNT" -gt 0 ]; then
        {
          echo "**买方席位 TOP$BUY_CNT** (按净买额降序):"
          echo
          echo "| 营业部 | 买入(万) | 卖出(万) | 净买入(万) |"
          echo "|---|---:|---:|---:|"
          echo "$BUY" | jq -r '
            .result.data[]? |
            [
              .OPERATEDEPT_NAME,
              ((.BUY // 0) / 10000 | floor | tostring),
              ((.SELL // 0) / 10000 | floor | tostring),
              ((.NET // 0) / 10000 | floor | tostring)
            ] | @tsv
          ' | awk -F'\t' '{ printf "| %s | %s | %s | %s |\n", $1,$2,$3,$4 }'
          echo
        } >> "$OUT"
        echo "  ✅ $CODE 买方 $BUY_CNT 个席位"
      else
        echo "_当日未上龙虎榜_" >> "$OUT"
        echo "  ℹ️  $CODE 当日未上龙虎榜"
        echo >> "$OUT"
        continue
      fi
    fi

    # 卖方席位 (按净卖额排序, 取 TOP10)
    SELL2_URL="https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_BILLBOARD_DAILYDETAILSSELL&columns=ALL&filter=(SECURITY_CODE%3D%22$CODE%22)(TRADE_DATE%3E%3D%27$DATE%27)(TRADE_DATE%3C%3D%27$DATE%27)&pageNumber=1&pageSize=15&sortColumns=NET&sortTypes=1"
    SELL2=$(fetch "$SELL2_URL")

    if [ -n "$SELL2" ] && echo "$SELL2" | jq -e '.result.data' >/dev/null 2>&1; then
      SELL_CNT=$(echo "$SELL2" | jq '.result.data | length')
      if [ "$SELL_CNT" -gt 0 ]; then
        {
          echo "**卖方席位 TOP$SELL_CNT** (按净卖额升序, 数字越负越大):"
          echo
          echo "| 营业部 | 买入(万) | 卖出(万) | 净额(万) |"
          echo "|---|---:|---:|---:|"
          echo "$SELL2" | jq -r '
            .result.data[]? |
            [
              .OPERATEDEPT_NAME,
              ((.BUY // 0) / 10000 | floor | tostring),
              ((.SELL // 0) / 10000 | floor | tostring),
              ((.NET // 0) / 10000 | floor | tostring)
            ] | @tsv
          ' | awk -F'\t' '{ printf "| %s | %s | %s | %s |\n", $1,$2,$3,$4 }'
          echo
        } >> "$OUT"
      fi
    fi

    # 顶级游资识别提示
    {
      echo "**🏆 席位识别提示** (在席位名搜索这些关键词):"
      echo "- ✅ 章盟主 = \"中信证券股份有限公司上海溧阳路\""
      echo "- ✅ 作手新一 = \"国泰海通证券股份有限公司苏州桐泾北路\""
      echo "- ✅ 紫阳东路 = \"国泰海通证券股份有限公司武汉紫阳东路\""
      echo "- ✅ 华鑫上海分公司 (一线游资)"
      echo "- ⚠️ 温州帮 = 温州/宁波各路营业部 (出现在卖方=风险)"
      echo "- ⚠️ 量化打板 = 国新证券北京中关村 / 高盛(中国) / 瑞银证券花园石桥路"
      echo
    } >> "$OUT"
  done
fi

# ─── 末尾参考 ───
{
  echo "---"
  echo
  echo "## 📋 复盘 Checklist"
  echo
  echo "- [ ] 涨停板池 (脚本未抓, 见九阳公社/同花顺): https://q.10jqka.com.cn/zs/"
  echo "- [ ] 板块梯队 (东财): http://quote.eastmoney.com/center/boardlist.html"
  echo "- [ ] 业绩雷扫描 (候选股最近5日披露): https://data.eastmoney.com/notices/"
  echo "- [ ] 顶级游资动向 → 章盟主/葛老大/作手新一/紫阳东路 (见上方)"
  echo "- [ ] 温州帮卖单 → 出现在卖方 TOP3 就避雷"
  echo "- [ ] 六维评分 → strategies/晋级股精选策略-v1.0.md"
  echo "- [ ] 输出明日操作单"
  echo
  echo "## 🔗 完整链接库"
  echo "- references/A股复盘网址库.md"
  echo "- strategies/晋级股精选策略-v1.0.md"
} >> "$OUT"

echo
echo "✅ 完成! 报告: $OUT"
