#!/usr/bin/env python3
"""趋势顶底 + RSI三线 + 均线成交量 指标计算模块

根据 TDX 公式源码精确实现。
趋势顶底公式：
  长期线(A) = MA(-100*(HHV(H,34)-C)/(HHV(H,34)-LLV(L,34)), 19) + 100
  短期线(B) = -100*(HHV(H,14)-C)/(HHV(H,14)-LLV(L,14)) + 100
  中期线(D) = EMA(-100*(HHV(H,34)-C)/(HHV(H,34)-LLV(L,34)), 4) + 100

解读：指标值反映价格在区间内的位置（高值=价格处于区间高位/超买，低值=价格处于区间低位/超卖）
"""

import numpy as np
import pandas as pd


def calc_trend_top_bottom(df: pd.DataFrame) -> pd.DataFrame:
    """计算趋势顶底三条线（长期线、短期线、中期线）。

    Args:
        df: 含 'high', 'low', 'close' 列的 DataFrame

    Returns:
        添加 long_line, short_line, mid_line 列的 DataFrame
    """
    high = df['high'].values.astype(np.float64)
    low = df['low'].values.astype(np.float64)
    close = df['close'].values.astype(np.float64)

    n = len(df)

    # 短期线(B): 14日区间价格位置
    # raw = -100 * (HHV(H,14)-C) / (HHV(H,14)-LLV(L,14))
    short_line = np.full(n, np.nan)
    for i in range(13, n):
        hhv14 = np.max(high[i - 13 : i + 1])
        llv14 = np.min(low[i - 13 : i + 1])
        denom = hhv14 - llv14
        if denom == 0:
            short_line[i] = 50.0  # 区间为零时中性值
        else:
            raw = -100.0 * (hhv14 - close[i]) / denom
            short_line[i] = raw + 100.0

    # 长期线(A) & 中期线(D) 共用底层 raw_34
    # raw_34 = -100 * (HHV(H,34)-C) / (HHV(H,34)-LLV(L,34))
    raw_34 = np.full(n, np.nan)
    for i in range(33, n):
        hhv34 = np.max(high[i - 33 : i + 1])
        llv34 = np.min(low[i - 33 : i + 1])
        denom = hhv34 - llv34
        if denom == 0:
            raw_34[i] = 0.0
        else:
            raw_34[i] = -100.0 * (hhv34 - close[i]) / denom
        raw_34[i] += 100.0  # 先不加 100，留给 MA/EMA 处理

    # 等等，公式是 MA(raw_34 + 100) 还是 MA(raw_34) + 100？两者等价，因为+100是线性变换。
    # raw_34 已经+100 了，接下来 MA/EMA

    # 长期线: MA(raw_34, 19)
    long_line = pd.Series(raw_34).rolling(window=19, min_periods=1).mean().values

    # 中期线: EMA(raw_34, 4)
    mid_line = pd.Series(raw_34).ewm(span=4, adjust=False, min_periods=1).mean().values

    df = df.copy()
    df['ttb_long'] = long_line   # 长期线
    df['ttb_short'] = short_line  # 短期线
    df['ttb_mid'] = mid_line      # 中期线

    # TTB 底部/顶部区域信号
    df = _calc_ttb_signals(df)

    return df


def _calc_ttb_signals(df: pd.DataFrame) -> pd.DataFrame:
    """根据趋势顶底公式计算底部区域、顶部区域、低位金叉信号。

    底部区域:
      (长期线<12 AND 中期线<8 AND (短期线<7.2 OR REF(短期线,1)<5)
       AND (中期线>REF(中期线,1) OR 短期线>REF(短期线,1)))
      OR (长期线<8 AND 中期线<7 AND 短期线<15 AND 短期线>REF(短期线,1))
      OR (长期线<10 AND 中期线<7 AND 短期线<1)

    顶部区域:
      (中期线<REF(中期线,1) AND REF(中期线,1)>80)
      AND (REF(短期线,1)>95 OR REF(短期线,2)>95)
      AND 长期线>60 AND 短期线<83.5
      AND 短期线<中期线 AND 短期线<长期线+4

    低位金叉:
      50*(长期线<15 AND REF(长期线,1)<15 AND 中期线<18
          AND 短期线>REF(短期线,1) AND CROSS(短期线,长期线)
          AND 短期线>中期线
          AND (REF(短期线,1)<5 OR REF(短期线,2)<5)
          AND (中期线>=长期线 OR REF(短期线,1)<1))
    """
    n = len(df)
    long_ = df['ttb_long'].values
    short_ = df['ttb_short'].values
    mid_ = df['ttb_mid'].values

    bottom_zone = np.zeros(n, dtype=bool)
    top_zone = np.zeros(n, dtype=bool)
    low_golden_cross = np.zeros(n, dtype=float)

    for i in range(1, n):
        # --- 底部区域 ---
        cond1 = (
            long_[i] < 12 and mid_[i] < 8
            and (short_[i] < 7.2 or short_[i - 1] < 5)
            and (mid_[i] > mid_[i - 1] or short_[i] > short_[i - 1])
        )
        cond2 = (
            long_[i] < 8 and mid_[i] < 7
            and short_[i] < 15 and short_[i] > short_[i - 1]
        )
        cond3 = long_[i] < 10 and mid_[i] < 7 and short_[i] < 1
        bottom_zone[i] = cond1 or cond2 or cond3

        # --- 顶部区域 ---
        ref_short1_gt_95 = (i >= 1 and short_[i - 1] > 95)
        ref_short2_gt_95 = (i >= 2 and short_[i - 2] > 95)
        top_cond = (
            mid_[i] < mid_[i - 1] and mid_[i - 1] > 80
            and (ref_short1_gt_95 or ref_short2_gt_95)
            and long_[i] > 60 and short_[i] < 83.5
            and short_[i] < mid_[i] and short_[i] < long_[i] + 4
        )
        top_zone[i] = top_cond

        # --- 低位金叉 (CROSS(短期线, 长期线)) ---
        cross_up = (i >= 1 and short_[i] > long_[i] and short_[i - 1] <= long_[i - 1])
        ref_short1_lt_5 = (i >= 1 and short_[i - 1] < 5)
        ref_short2_lt_5 = (i >= 2 and short_[i - 2] < 5)
        golden = (
            long_[i] < 15 and long_[i - 1] < 15
            and mid_[i] < 18
            and short_[i] > short_[i - 1]
            and cross_up
            and short_[i] > mid_[i]
            and (ref_short1_lt_5 or ref_short2_lt_5)
            and (mid_[i] >= long_[i] or (i >= 1 and short_[i - 1] < 1))
        )
        low_golden_cross[i] = 50.0 if golden else 0.0

    df = df.copy()
    df['ttb_bottom'] = bottom_zone
    df['ttb_top'] = top_zone
    df['ttb_golden'] = low_golden_cross > 0
    return df


def calc_rsi(df: pd.DataFrame, periods=(6, 12, 24)) -> pd.DataFrame:
    """计算 RSI 多周期。

    Args:
        df: 含 'close' 列的 DataFrame
        periods: RSI 周期元组

    Returns:
        添加 rsi_{p} 列的 DataFrame
    """
    df = df.copy()
    close = df['close'].values.astype(np.float64)
    for p in periods:
        delta = np.diff(close, prepend=close[0])
        gain = np.where(delta > 0, delta, 0)
        loss = np.where(delta < 0, -delta, 0)

        # 使用 SMA 方式（Wilder's RSI）
        avg_gain = pd.Series(gain).ewm(alpha=1 / p, adjust=False, min_periods=p).mean().values
        avg_loss = pd.Series(loss).ewm(alpha=1 / p, adjust=False, min_periods=p).mean().values

        rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain, np.nan), where=avg_loss != 0)
        rsi = 100.0 - 100.0 / (1.0 + rs)
        rsi[: p - 1] = np.nan
        df[f'rsi{p}'] = rsi

    return df


def calc_ma(df: pd.DataFrame, periods=(5, 10, 20, 30)) -> pd.DataFrame:
    """计算简单移动均线。"""
    df = df.copy()
    for p in periods:
        df[f'ma{p}'] = df['close'].rolling(window=p, min_periods=p).mean()
    return df


def calc_volume_ratio(df: pd.DataFrame, period=5) -> pd.DataFrame:
    """成交量与 N 日均量比值。"""
    df = df.copy()
    df['vol_ma5'] = df['volume'].rolling(window=period, min_periods=period).mean()
    df['vol_ratio'] = df['volume'] / df['vol_ma5']
    return df


def calc_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """一站式计算所有指标。

    Args:
        df: 含 open, high, low, close, volume 列的 DataFrame，按日期升序排列

    Returns:
        添加全部指标列的 DataFrame
    """
    df = calc_trend_top_bottom(df)
    df = calc_rsi(df)
    df = calc_ma(df)
    df = calc_volume_ratio(df)
    return df
