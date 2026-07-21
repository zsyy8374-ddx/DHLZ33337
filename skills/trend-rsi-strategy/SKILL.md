---
name: trend-rsi-strategy
description: |
  趋势顶底 + RSI三线 + 均线成交量组合战法 v2.0：量化回测、信号扫描与选股。
  基于董哥的「源码实战版」，四套战法——底部观察（只看不买）、
  低位金叉试买（小仓）、趋势修复加仓（主力）、高位减仓（风控）。
  用于回测历史表现、扫描当日买入信号、评估个股适配度。
  触发词：趋势顶底、RSI三线、低位金叉、趋势修复、TTB回测、trend rsi
---

# 趋势顶底RSI三线组合战法 v2.0

基于董哥「源码实战版」文档，对齐四大战法：
1. 底部观察 — TTD 底部区域触发，加入自选，不买
2. 低位金叉试买 — TTD 低位金叉触发，小仓试买
3. 趋势修复加仓 — 中期线站上 50 + RSI 多头 + 均线确认（主力战法）
4. 高位减仓 — TTD 顶部区域触发，逐步减仓/离场

## 快速开始

```bash
# 趋势修复回测（主力战法）
python3 scripts/backtest.py --code 600330 --strategy trend_repair

# 全战法对比
python3 scripts/backtest.py --code 600330 --strategy all

# 今日扫描
python3 scripts/backtest.py --pool-file /tmp/watch.txt --scan --strategy all

# 调参数
python3 scripts/backtest.py --code 600330 --stop -8 --target 20 --hold 15 --cooldown 10
```

## 战法说明

### 底部观察 (watch)
TTD 底部区域绿柱 → 加入自选观察。信号 1=底部区域，2=短期抬头，3=放量异动。**只看不买**，等低位金叉或趋势修复后再出手。

### 低位金叉试买 (golden_cross)
TTD 低位金叉信号 → 可小仓试买。激进=金叉当天尾盘，稳健=站上 5/10 日线后。信号稀少但质量高。

### 趋势修复加仓 (trend_repair) ★ 主力
中期线近期上穿 50 + RSI12>50 + RSI24 走平 + 股价站上 20 日线 + RSI 三线多头 + 放量。
- 等级 1：回踩买点（缩量回踩 MA10/20 + 放量阳线）
- 等级 2：突破加仓（中期线首次站上 50，仅触发一次）

### 高位减仓 (exit)
等级 1=减仓（顶部区域/短期线下穿中期线/RSI 死叉+破 10 日线）
等级 2=离场（破 20 日线+中期线拐头/顶背离）

## 回测参数

| 参数 | 默认 | 说明 |
|------|------|------|
| --strategy | all | golden_cross/trend_repair/watch/all |
| --days | 500 | 回看交易日 |
| --hold | 10 | 最大持仓天数 |
| --stop | -5.0 | 止损% |
| --target | 15.0 | 止盈% |
| --cooldown | 5 | 信号冷却天数 |

## 数据源

多源自动降级：akshare → eastmoney → sina

## 模块说明

- `indicators.py` — TTD三线、RSI三线、均线、量比计算（按TDX公式源码精确实现）
- `signals.py` — 四大战法信号生成 v2.0
- `backtest.py` — 回测引擎 + CLI + 扫描

修改战法条件改 signals.py，加新战法改 signals.py + backtest.py 的 sig_map。
