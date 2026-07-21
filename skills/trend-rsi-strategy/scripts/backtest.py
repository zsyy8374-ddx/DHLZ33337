#!/usr/bin/env python3
"""趋势顶底RSI三线组合战法 — 回测引擎

用法：
    python3 backtest.py --code 600330 --days 500          # 单只股票回测
    python3 backtest.py --pool sh50 --days 250             # 沪深300池子
    python3 backtest.py --code 002805 --strategy pullback   # 指定战法
    python3 backtest.py --scan --strategy pullback --date 2026-07-21  # 当天扫描

战法参数：
    golden_cross — 低位金叉试买
    trend_repair — 趋势修复加仓（默认，推荐）
    watch        — 底部观察（仅扫描，不回测）
    all          — 全部战法分别回测
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

# 同目录模块
from indicators import calc_all_indicators
from signals import generate_all_signals

# ── 数据获取 ──────────────────────────────────────────────


def fetch_daily_kline(code: str, days: int = 500, source: str = "akshare") -> pd.DataFrame:
    """获取 A 股日 K 线数据。

    Args:
        code: A股代码，如 '600330', '002805'
        days: 获取天数
        source: 'akshare' | 'sina' | 'eastmoney'

    Returns:
        DataFrame: date(索引), open, high, low, close, volume, amount
    """
    try:
        if source == "akshare":
            return _fetch_akshare(code, days)
        elif source == "eastmoney":
            return _fetch_eastmoney(code, days)
        else:
            return _fetch_sina(code, days)
    except Exception as e:
        print(f"[WARN] {source} 获取 {code} 失败: {e}，尝试备用源")
        # 自动降级
        for fallback in ["eastmoney", "sina", "akshare"]:
            if fallback == source:
                continue
            try:
                if fallback == "akshare":
                    return _fetch_akshare(code, days)
                elif fallback == "eastmoney":
                    return _fetch_eastmoney(code, days)
                else:
                    return _fetch_sina(code, days)
            except Exception:
                continue
        raise RuntimeError(f"所有数据源均无法获取 {code}")


def _code_prefix(code: str) -> str:
    """判断交易所前缀: sh/sz"""
    return "sh" if code.startswith(("6", "9")) else "sz"


def _fetch_akshare(code: str, days: int) -> pd.DataFrame:
    import akshare as ak
    prefix = _code_prefix(code)
    sym = f"{prefix}{code}"
    df = ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
    df = df.rename(columns={
        "日期": "date", "开盘": "open", "最高": "high",
        "最低": "low", "收盘": "close", "成交量": "volume",
        "成交额": "amount"
    })
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").tail(days)
    df = df.set_index("date")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def _fetch_eastmoney(code: str, days: int) -> pd.DataFrame:
    """东方财富 K 线 API（免费，无需登录）。"""
    import urllib.request
    prefix = _code_prefix(code)
    secid = f"{1 if prefix == 'sh' else 0}.{code}"
    # 前复权
    url = (
        f"https://push2his.eastmoney.com/api/qt/stock/kline/get?"
        f"secid={secid}&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58"
        f"&klt=101&fqt=1&end=20500101&lmt={days}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if data.get("data") is None or data["data"].get("klines") is None:
        raise RuntimeError(f"东方财富返回空数据: {code}")
    rows = []
    for line in data["data"]["klines"]:
        parts = line.split(",")
        rows.append({
            "date": pd.Timestamp(parts[0]),
            "open": float(parts[1]),
            "close": float(parts[2]),
            "high": float(parts[3]),
            "low": float(parts[4]),
            "volume": float(parts[5]),
            "amount": float(parts[6]),
        })
    df = pd.DataFrame(rows).sort_values("date").set_index("date")
    return df


def _fetch_sina(code: str, days: int) -> pd.DataFrame:
    """新浪财经 K 线 API。"""
    import urllib.request
    prefix = _code_prefix(code)
    sym = f"{prefix}{code}"
    # 日K前复权，取足够多数据
    url = f"https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData?symbol={sym}&scale=240&ma=no&datalen={days}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode())
    if not data:
        raise RuntimeError(f"新浪返回空数据: {code}")
    rows = []
    for item in data:
        rows.append({
            "date": pd.Timestamp(item["day"]),
            "open": float(item["open"]),
            "high": float(item["high"]),
            "low": float(item["low"]),
            "close": float(item["close"]),
            "volume": float(item["volume"]),
        })
    df = pd.DataFrame(rows).sort_values("date").set_index("date")
    return df


# ── 回测核心 ──────────────────────────────────────────────


def run_backtest(
    df: pd.DataFrame,
    strategy: str = "all",
    hold_days: int = 10,
    stop_loss_pct: float = -5.0,
    take_profit_pct: float = 15.0,
    max_positions: int = 5,
    cooldown_days: int = 5,
    commission: float = 0.0003,
) -> dict:
    """执行回测。

    Args:
        df: 含全部指标和信号的 DataFrame
        strategy: 'reversal' | 'pullback' | 'breakout' | 'all'
        hold_days: 最大持仓天数
        stop_loss_pct: 止损百分比 (负数)
        take_profit_pct: 止盈百分比 (正数)
        max_positions: 最大同时持仓数
        commission: 手续费率

    Returns:
        dict: 含 trades, metrics 的完整回测结果
    """
    # 计算指标和信号
    df = calc_all_indicators(df)
    df = generate_all_signals(df)
    df = df.reset_index()

    # 信号列映射 v2.0
    # watch 是观察模式，不做回测
    sig_map = {
        "golden_cross": "signal_golden_cross",
        "trend_repair": "signal_trend_repair",
    }

    if strategy == "all":
        strategies = list(sig_map.keys())
    else:
        strategies = [strategy]

    all_results = {}
    for st in strategies:
        all_results[st] = _backtest_single(df, sig_map[st], hold_days,
                                           stop_loss_pct, take_profit_pct,
                                           max_positions, cooldown_days, commission)
    return all_results


def _backtest_single(
    df: pd.DataFrame,
    signal_col: str,
    hold_days: int,
    stop_loss: float,
    take_profit: float,
    max_pos: int,
    cooldown: int,
    commission: float,
) -> dict:
    """单策略回测。"""
    n = len(df)
    trades = []
    positions = []
    last_entry_idx = -cooldown  # cooldown tracking
    cash_curve = [1.0]

    for i in range(1, n):
        row = df.iloc[i]
        signal = row.get(signal_col, 0)
        close_price = row['close']
        high_price = row['high']
        low_price = row['low']

        # 检查持仓出场
        remaining = []
        for pos in positions:
            exit_price = None
            exit_reason = ""
            exit_idx = i

            # 止损
            if low_price <= pos['stop_price']:
                exit_price = pos['stop_price']
                exit_reason = "止损"
            # 止盈
            elif high_price >= pos['target_price']:
                exit_price = pos['target_price']
                exit_reason = "止盈"
            # 时间到期
            elif i - pos['entry_idx'] >= hold_days:
                exit_price = close_price
                exit_reason = "到期"
            # 出场信号（仅对 pullback/breakout，reversal 无 exit signal 强制退出）
            # 这里统一用到期或止损止盈

            if exit_price is not None:
                ret = (exit_price - pos['entry_price']) / pos['entry_price']
                ret_net = ret - commission * 2  # 买+卖
                trades.append({
                    "entry_date": str(df.iloc[pos['entry_idx']].get('date', pos['entry_idx'])),
                    "exit_date": str(row.get('date', exit_idx)),
                    "entry_price": round(pos['entry_price'], 2),
                    "exit_price": round(exit_price, 2),
                    "return_pct": round(ret_net * 100, 2),
                    "reason": exit_reason,
                    "hold_days": exit_idx - pos['entry_idx'],
                    "strategy_type": pos.get('strategy_type', ''),
                })
                cash_curve.append(cash_curve[-1] * (1 + ret_net))
            else:
                remaining.append(pos)

        positions = remaining

        # 入场 v2.0: 信号值 1=激进, 2=稳健/加仓，带冷却期
        if signal > 0 and len(positions) < max_pos and (i - last_entry_idx) > cooldown:
            last_entry_idx = i
            entry_price = close_price
            sl_price = entry_price * (1 + stop_loss / 100)
            tp_price = entry_price * (1 + take_profit / 100)
            stype = {1: "激进", 2: "稳健"}.get(signal, f"L{signal}")
            positions.append({
                "entry_idx": i,
                "entry_price": entry_price,
                "stop_price": sl_price,
                "target_price": tp_price,
                "strategy_type": stype,
            })

    # 平掉未出场持仓
    last_row = df.iloc[-1]
    last_close = last_row['close']
    last_date = str(last_row.get('date', n - 1))
    for pos in positions:
        ret = (last_close - pos['entry_price']) / pos['entry_price']
        ret_net = ret - commission * 2
        trades.append({
            "entry_date": str(df.iloc[pos['entry_idx']].get('date', pos['entry_idx'])),
            "exit_date": last_date,
            "entry_price": round(pos['entry_price'], 2),
            "exit_price": round(last_close, 2),
            "return_pct": round(ret_net * 100, 2),
            "reason": "期末平仓",
            "hold_days": n - 1 - pos['entry_idx'],
            "strategy_type": pos.get('strategy_type', ''),
        })
        cash_curve.append(cash_curve[-1] * (1 + ret_net))

    return _compute_metrics(trades, cash_curve)


def _compute_metrics(trades: list, cash_curve: list) -> dict:
    """计算回测指标。"""
    if not trades:
        return {
            "total_trades": 0,
            "win_rate": 0,
            "avg_return": 0,
            "max_return": 0,
            "min_return": 0,
            "avg_hold_days": 0,
            "total_return": 0,
            "max_drawdown": 0,
            "profit_factor": 0,
            "trades": [],
        }

    returns = [t["return_pct"] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    # 累计收益曲线
    curve = np.array(cash_curve)
    peak = np.maximum.accumulate(curve)
    drawdown = (curve - peak) / peak

    total_profit = sum(r for r in returns if r > 0)
    total_loss = abs(sum(r for r in returns if r <= 0))

    return {
        "total_trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "avg_return": round(np.mean(returns), 2),
        "median_return": round(np.median(returns), 2),
        "max_return": round(max(returns), 2),
        "min_return": round(min(returns), 2),
        "avg_hold_days": round(np.mean([t["hold_days"] for t in trades]), 1),
        "total_return": round((curve[-1] - 1) * 100, 2),
        "max_drawdown": round(min(drawdown) * 100, 2),
        "profit_factor": round(total_profit / total_loss, 2) if total_loss > 0 else float("inf"),
        "sharpe_like": round(np.mean(returns) / (np.std(returns) + 1e-9) * np.sqrt(252 / max(np.mean([t["hold_days"] for t in trades]), 1)), 2),
        "exit_reasons": _count_reasons(trades),
        "trades": trades,
    }


def _count_reasons(trades: list) -> dict:
    from collections import Counter
    return dict(Counter(t["reason"] for t in trades))


# ── 当天扫描 ──────────────────────────────────────────────


def scan_today(
    codes: list[str],
    strategy: str = "pullback",
    days: int = 500,
) -> pd.DataFrame:
    """扫描多只股票当天的信号。

    Returns:
        DataFrame: code, name(if available), signal_type, close, indicators...
    """
    results = []
    for code in codes:
        try:
            df = fetch_daily_kline(code, days)
            if len(df) < 100:
                continue
            df = calc_all_indicators(df)
            df = generate_all_signals(df)

            last = df.iloc[-1]
            last_date = df.index[-1]

            sig_map = {
                "golden_cross": "signal_golden_cross",
                "trend_repair": "signal_trend_repair",
                "watch": "signal_bottom_watch",
            }

            if strategy == "all":
                strategies = list(sig_map.keys())
            else:
                strategies = [strategy]

            for st in strategies:
                sig_val = last.get(sig_map[st], 0)
                if sig_val > 0:
                    if st == "watch":
                        sw = {1: "底部区域", 2: "短期抬头", 3: "放量异动"}
                        stype = sw.get(sig_val, f"等级{sig_val}")
                    elif st == "golden_cross":
                        stype = "激进买点" if sig_val == 1 else "稳健买点"
                    elif st == "trend_repair":
                        stype = "回踩买点" if sig_val == 1 else "突破加仓"
                    else:
                        stype = str(sig_val)

                    results.append({
                        "code": code,
                        "date": str(last_date.date()),
                        "strategy": st,
                        "signal_type": stype,
                        "close": round(last['close'], 2),
                        "ttb_mid": round(last.get('ttb_mid', 0), 1),
                        "ttb_short": round(last.get('ttb_short', 0), 1),
                        "rsi6": round(last.get('rsi6', 0), 1),
                        "rsi12": round(last.get('rsi12', 0), 1),
                        "rsi24": round(last.get('rsi24', 0), 1),
                        "vol_ratio": round(last.get('vol_ratio', 0), 2),
                    })
        except Exception as e:
            print(f"[SKIP] {code}: {e}", file=sys.stderr)
            continue

    return pd.DataFrame(results)


# ── 常用股票池 ─────────────────────────────────────────────


STOCK_POOLS = {
    "hs300": [
        "600519", "000858", "601318", "600036", "000333", "600276", "601012",
        "600900", "002415", "300750", "600585", "000651", "601888", "600809",
        "000002", "300059", "600030", "000725", "002475", "600887",
        "601166", "000568", "600048", "002714", "601398", "603259",
        "000063", "600309", "300124", "002594",
    ],
    "sh50": [
        "600519", "601318", "600036", "600276", "600900", "600585",
        "601166", "601398", "600030", "601888", "600809", "600887",
    ],
    "my": ["600330", "002805"],  # 董哥持仓
}

# ── CLI ───────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="趋势顶底RSI三线战法回测")
    parser.add_argument("--code", help="单只股票代码")
    parser.add_argument("--pool", choices=list(STOCK_POOLS.keys()), help="股票池")
    parser.add_argument("--pool-file", help="股票池文件（每行一个代码）")
    parser.add_argument("--strategy", default="all",
                        choices=["golden_cross", "trend_repair", "watch", "all"],
                        help="战法 (default: all)")
    parser.add_argument("--days", type=int, default=500, help="回看天数")
    parser.add_argument("--hold", type=int, default=10, help="最大持仓天数")
    parser.add_argument("--stop", type=float, default=-5.0, help="止损%")
    parser.add_argument("--target", type=float, default=15.0, help="止盈%")
    parser.add_argument("--scan", action="store_true", help="当天扫描模式")
    parser.add_argument("--scan-date", help="扫描日期 YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="JSON输出")
    parser.add_argument("--csv", help="保存到CSV文件")

    args = parser.parse_args()

    # 确定股票池
    codes = []
    if args.code:
        codes = [args.code]
    elif args.pool:
        codes = STOCK_POOLS.get(args.pool, [])
    elif args.pool_file:
        codes = [line.strip() for line in open(args.pool_file) if line.strip()]
    else:
        codes = ["600330"]  # 默认天通股份

    if args.scan or args.scan_date:
        # 扫描模式
        df_signals = scan_today(codes, args.strategy, args.days)
        if df_signals.empty:
            print("未发现买入信号")
            return
        if args.json:
            print(df_signals.to_json(orient="records", force_ascii=False, indent=2))
        elif args.csv:
            df_signals.to_csv(args.csv, index=False, encoding="utf-8-sig")
            print(f"已保存 {args.csv}")
        else:
            pd.set_option("display.max_columns", 20)
            pd.set_option("display.width", 200)
            pd.set_option("display.max_colwidth", 20)
            print(df_signals.to_string(index=False))
        return

    # 回测模式
    all_trades = []
    for code in codes:
        print(f"\n{'='*60}")
        print(f"  {code} 回测中...")
        print(f"{'='*60}")

        try:
            df = fetch_daily_kline(code, args.days)
        except Exception as e:
            print(f"  [ERROR] 数据获取失败: {e}")
            continue

        print(f"  数据范围: {df.index[0].date()} ~ {df.index[-1].date()} ({len(df)} 条)")

        results = run_backtest(df, args.strategy, args.hold, args.stop, args.target)

        for st_name, res in results.items():
            m = res
            print(f"\n  ── {st_name} ──")
            print(f"  交易次数: {m['total_trades']}  |  胜率: {m['win_rate']}%")
            print(f"  平均收益: {m['avg_return']}%  |  中位数: {m['median_return']}%")
            print(f"  最大单笔: {m['max_return']}%  |  最小单笔: {m['min_return']}%")
            print(f"  平均持仓: {m['avg_hold_days']}天")
            print(f"  总收益: {m['total_return']}%  |  最大回撤: {m['max_drawdown']}%")
            print(f"  盈亏比: {m['profit_factor']}  |  夏普(类): {m['sharpe_like']}")
            if m.get('exit_reasons'):
                print(f"  出场分布: {m['exit_reasons']}")

            for t in m.get("trades", []):
                t["code"] = code
                t["strategy"] = st_name
            all_trades.extend(m.get("trades", []))

    if args.csv and all_trades:
        pd.DataFrame(all_trades).to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"\n交易明细已保存 {args.csv}")

    if args.json and all_trades:
        print(json.dumps(all_trades, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
