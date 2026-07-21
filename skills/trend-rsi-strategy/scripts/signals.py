#!/usr/bin/env python3
"""趋势顶底RSI三线组合战法 — 信号生成模块 v2.0

对齐「源码实战版」四大战法：
1. 底部观察 — TTD 底部区域绿柱触发，只看不买，加入自选
2. 低位金叉试买 — TTD 低位金叉触发，小仓试买
3. 趋势修复加仓 — TTD 中期线站上 50 + RSI 多头 + 均线确认
4. 高位减仓 — TTD 顶部区域触发，逐步减仓/离场

信号值含义：
- signal_bottom_watch: 0/1/2/3 (观察/短期抬头/不创新低/放量异动)
- signal_golden_cross: 0/1/2 (无/激进买点/稳健买点)
- signal_trend_repair: 0/1/2 (无/回踩买点/突破加仓)
- signal_exit: 0/1/2 (无/减仓/离场)
"""

import numpy as np
import pandas as pd


def _prepare(df: pd.DataFrame) -> pd.DataFrame:
    required = ['ttb_long', 'ttb_short', 'ttb_mid', 'ttb_bottom',
                'ttb_golden', 'ttb_top',
                'rsi6', 'rsi12', 'rsi24', 'ma5', 'ma10', 'ma20',
                'vol_ratio', 'close', 'high', 'low', 'volume']
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"缺少列: {missing}。请先运行 calc_all_indicators()")
    return df


# ── 1. 底部观察战法 ──────────────────────────────────────

def signal_bottom_watch(df: pd.DataFrame) -> pd.Series:
    """底部观察战法 — TTD 底部区域绿柱出现后，加入自选观察。

    信号等级：
      0 = 无
      1 = 底部区域出现，加入自选观察
      2 = 短期线继续上行 + 股价不破前低 → 继续观察
      3 = 短期线上行 + 缩量转放量 → 关注度提高

    注意：此战法只提供观察信号，不直接买入。
    """
    df = _prepare(df)
    n = len(df)
    signals = pd.Series(np.zeros(n, dtype=int), index=df.index)

    ttb_bottom = df['ttb_bottom'].values
    ttb_short = df['ttb_short'].values
    low = df['low'].values
    vol_ratio = df['vol_ratio'].values

    for i in range(3, n):
        # 等级 1：底部区域出现
        if ttb_bottom[i]:
            signals.iloc[i] = 1

        # 等级 2：底部区域出现后，短期线继续上行 + 不破前低
        if ttb_bottom[i - 1] or (i >= 2 and ttb_bottom[i - 2]):
            if ttb_short[i] > ttb_short[i - 1] and low[i] >= low[i - 3:i].min():
                signals.iloc[i] = max(signals.iloc[i], 2)

        # 等级 3：短期线上行 + 缩量转温和放量
        if signals.iloc[i] >= 2:
            if vol_ratio[i] > 0.8 and vol_ratio[i] > vol_ratio[i - 1]:
                signals.iloc[i] = max(signals.iloc[i], 3)

    return signals


# ── 2. 低位金叉试买战法 ──────────────────────────────────

def signal_golden_cross(df: pd.DataFrame) -> pd.Series:
    """低位金叉试买战法 — TTD 低位金叉触发。

    激进买点(1)：低位金叉当天尾盘小仓试买
    稳健买点(2)：低位金叉后股价站上 5/10 日线 + 收盘站稳

    加仓条件(在 signal_trend_repair 中处理)：
      中期线站上 20 + 放量突破下降趋势线或小平台
    """
    df = _prepare(df)
    n = len(df)
    signals = pd.Series(np.zeros(n, dtype=int), index=df.index)

    ttb_golden = df['ttb_golden'].values
    close = df['close'].values
    ma5 = df['ma5'].values
    ma10 = df['ma10'].values

    for i in range(2, n):
        if not ttb_golden[i]:
            continue

        # 激进买点：金叉当天 = 1
        signals.iloc[i] = 1

        # 稳健买点：金叉后几天内站上 5/10 日线
        for j in range(i, min(i + 5, n)):
            if np.isfinite(ma5[j]) and np.isfinite(ma10[j]):
                if close[j] > ma5[j] or close[j] > ma10[j]:
                    if signals.iloc[j] == 0:
                        signals.iloc[j] = 2
                    break

    return signals


# ── 3. 趋势修复加仓战法 ──────────────────────────────────

def signal_trend_repair(df: pd.DataFrame) -> pd.Series:
    """趋势修复加仓战法 — TTD 中期线站上 50 + RSI 多头 + 均线确认。

    信号等级：
      0 = 无
      1 = 回踩买点（缩量回踩 10/20 日线 + 放量阳线 + 短期线/RSI6 再次上拐）
      2 = 突破加仓（中期线 > 50 + 股价站上 20 日线 + RSI 三线多头 + 放量）
    """
    df = _prepare(df)
    n = len(df)
    signals = pd.Series(np.zeros(n, dtype=int), index=df.index)

    close = df['close'].values
    open_ = df['open'].values
    ttb_mid = df['ttb_mid'].values
    ttb_short = df['ttb_short'].values
    rsi6 = df['rsi6'].values
    rsi12 = df['rsi12'].values
    rsi24 = df['rsi24'].values
    ma5 = df['ma5'].values
    ma10 = df['ma10'].values
    ma20 = df['ma20'].values
    vol_ratio = df['vol_ratio'].values

    for i in range(10, n):
        if not np.isfinite([ttb_mid[i], rsi6[i], rsi12[i], rsi24[i], ma20[i], vol_ratio[i]]).all():
            continue

        # ── 等级 2：趋势修复确认加仓 ──
        # 中期线近期上穿 50（20天内）+ RSI12 > 50 + RSI24 走平向上
        # + 股价站上 20 日线 + RSI 三线多头 + 放量
        # 关键：必须是近期首次修复，不是已经在 50 上方很久
        recently_crossed_50 = any(
            ttb_mid[j] < 50 and ttb_mid[j + 1] >= 50
            for j in range(max(i - 20, 0), i)
        )
        mid_above_50 = ttb_mid[i] > 50
        rsi12_above_50 = rsi12[i] > 50
        rsi24_flat_up = i >= 3 and rsi24[i] >= rsi24[i - 3]
        price_above_ma20 = close[i] > ma20[i]
        rsi_bullish = rsi6[i] > rsi12[i] > rsi24[i]
        volume_ok = vol_ratio[i] > 1.3

        if (mid_above_50 and recently_crossed_50 and rsi12_above_50
                and rsi24_flat_up and price_above_ma20 and rsi_bullish and volume_ok):
            signals.iloc[i] = 2

        # ── 等级 1：回踩买点 ──
        # 前提：中期线从低位持续上行（>20 且在上升）
        # 回踩 10/20 日线缩量不破 → 放量阳线 + 短期线/RSI6 同步再上拐
        mid_rising = ttb_mid[i] > 20 and ttb_mid[i] > ttb_mid[i - 5]
        is_yang = close[i] > open_[i]
        above_ma5 = close[i] > ma5[i]
        volume_surge = vol_ratio[i] > 1.3

        # 之前缩量回踩
        near_ma = any(
            np.isfinite(ma10[j]) and np.isfinite(ma20[j])
            and abs(close[j] - ma10[j]) / ma10[j] < 0.03
            for j in range(max(i - 5, 0), i)
        )
        prev_vol_low = np.mean(vol_ratio[max(i - 3, 0):i]) < 1.2

        # 短期线/RSI6 再次上拐
        ttb_short_turn = ttb_short[i] > ttb_short[i - 1]
        rsi6_turn = rsi6[i] > rsi6[i - 1]

        if (mid_rising and is_yang and above_ma5 and volume_surge
                and near_ma and prev_vol_low
                and (ttb_short_turn or rsi6_turn)):
            signals.iloc[i] = max(signals.iloc[i], 1)

    return signals


# ── 4. 高位减仓战法 ──────────────────────────────────────

def signal_high_exit(df: pd.DataFrame) -> pd.Series:
    """高位减仓战法 — TTD 顶部区域触发。

    信号等级：
      0 = 无
      1 = 减仓（顶部区域出现 + 短期线高位回落跌破中期线）
      2 = 离场（跌破 20 日线 + 中期线拐头 + 顶背离）
    """
    df = _prepare(df)
    n = len(df)
    signals = pd.Series(np.zeros(n, dtype=int), index=df.index)

    close = df['close'].values
    high = df['high'].values
    ttb_mid = df['ttb_mid'].values
    ttb_short = df['ttb_short'].values
    ttb_top = df['ttb_top'].values
    rsi6 = df['rsi6'].values
    rsi12 = df['rsi12'].values
    rsi24 = df['rsi24'].values
    ma5 = df['ma5'].values
    ma10 = df['ma10'].values
    ma20 = df['ma20'].values
    vol_ratio = df['vol_ratio'].values

    for i in range(5, n):
        if not np.isfinite([ttb_mid[i], rsi6[i], rsi12[i], rsi24[i]]).all():
            continue

        # ── 等级 1：减仓 ──
        # 顶部区域出现
        # 或 短期线从高位回落跌破中期线
        top_signal = ttb_top[i]
        short_cross_below_mid = (
            ttb_short[i] < ttb_mid[i]
            and ttb_short[i - 1] >= ttb_mid[i - 1]
            and ttb_mid[i - 1] > 80
        )
        rsi_dead_cross = rsi6[i] < rsi12[i] and rsi6[i - 1] >= rsi12[i - 1]
        below_ma10 = np.isfinite(ma10[i]) and close[i] < ma10[i]

        if top_signal or short_cross_below_mid or (rsi_dead_cross and below_ma10):
            signals.iloc[i] = 1

        # ── 等级 2：离场 ──
        # 跌破 20 日线 + 中期线拐头
        below_ma20 = np.isfinite(ma20[i]) and close[i] < ma20[i]
        mid_turning = ttb_mid[i] < ttb_mid[i - 1] and ttb_mid[i - 1] > 70
        rsi24_turning = i >= 3 and rsi24[i] < rsi24[i - 1]

        # 顶背离：股价新高但 TTB 或 RSI12 不创新高
        lookback = min(20, i)
        recent_high = np.max(high[i - lookback:i])
        recent_ttb_high = np.max(ttb_mid[i - lookback:i])
        divergence = (close[i] >= recent_high * 0.98
                      and ttb_mid[i] < recent_ttb_high * 0.9)

        if ((below_ma20 and mid_turning)
                or (below_ma20 and rsi_dead_cross and rsi24_turning)
                or divergence):
            signals.iloc[i] = 2

    return signals


# ── 汇总 ──────────────────────────────────────────────────

def generate_all_signals(df: pd.DataFrame) -> pd.DataFrame:
    """生成全部策略信号 v2.0。

    Returns:
        DataFrame 含:
          signal_bottom_watch (0-3) — 底部观察
          signal_golden_cross (0-2) — 低位金叉试买
          signal_trend_repair (0-2) — 趋势修复加仓
          signal_exit (0-2)        — 高位减仓
    """
    df = df.copy()
    df['signal_bottom_watch'] = signal_bottom_watch(df)
    df['signal_golden_cross'] = signal_golden_cross(df)
    df['signal_trend_repair'] = signal_trend_repair(df)
    df['signal_exit'] = signal_high_exit(df)
    return df
