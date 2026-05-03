#!/usr/bin/env python3
"""
分析 wencai_yedan_history.py 拉的数据
- 隔夜单占比 → 当日涨停率
- 开盘封单占比 → 当日涨停率
- 封流比 → 次日不开板 (待加 D+1 数据)
"""
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import numpy as np

DATA_DIR = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def load_all():
    files = sorted(DATA_DIR.glob("yedan_*.csv"))
    dfs = []
    for f in files:
        df = pd.read_csv(f, dtype={"股票代码": str, "code": str, "date": str})
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

def is_zt(row):
    """判断当日涨停 (含 ST/20cm 板)"""
    code = str(row.get("code", ""))
    chg = row.get("chg_pct", 0)
    if pd.isna(chg):
        return False
    name = str(row.get("股票简称", ""))
    if "ST" in name:
        return chg >= 4.5
    # 创业板 / 科创板 / 北交所
    if code.startswith(("300", "688", "301", "8", "4", "9")):
        return chg >= 19.0  # 20cm
    return chg >= 9.5  # 主板

def bucket_analysis(df, col, buckets, label):
    print(f"\n=== {label} ({col}) ===")
    print(f"{'区间':<15} {'n':>6} {'涨停率':>10} {'平均涨幅':>10}")
    print("-" * 50)
    for lo, hi in buckets:
        if hi is None:
            mask = df[col] >= lo
            tag = f"≥{lo}%"
        else:
            mask = (df[col] >= lo) & (df[col] < hi)
            tag = f"{lo}-{hi}%"
        sub = df[mask]
        n = len(sub)
        if n == 0:
            print(f"{tag:<15} {n:>6} {'—':>10} {'—':>10}")
            continue
        zt_rate = sub["is_zt"].mean() * 100
        avg_chg = sub["chg_pct"].mean()
        print(f"{tag:<15} {n:>6} {zt_rate:>9.1f}% {avg_chg:>9.2f}%")

def main():
    df = load_all()
    print(f"总样本: {len(df)} 行 ({df['date'].nunique()} 天)")
    print(f"列名前 10: {list(df.columns[:10])}")

    # 数值化
    for c in ["yedan_pct", "open_seal_pct", "fenglu_ratio", "chg_pct", "auction_chg_pct"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    df["is_zt"] = df.apply(is_zt, axis=1)
    print(f"涨停样本: {df['is_zt'].sum()} / {len(df)} = {df['is_zt'].mean()*100:.1f}%")

    # 排除 ST (涨停阈值不同, 加污染)
    df_normal = df[~df["股票简称"].astype(str).str.contains("ST")]

    # 隔夜单占比
    bucket_analysis(df_normal, "yedan_pct", [
        (0, 1), (1, 5), (5, 10), (10, 20), (20, 50), (50, 100), (100, None)
    ], "隔夜单占比 (9:15 买二/流通)")

    # 开盘封单占比
    bucket_analysis(df_normal, "open_seal_pct", [
        (0, 1), (1, 5), (5, 10), (10, 20), (20, 30), (30, None)
    ], "开盘封单占比 (9:25 买一/流通)")

    # 封流比
    bucket_analysis(df_normal, "fenglu_ratio", [
        (0, 1), (1, 3), (3, 5), (5, 10), (10, 20), (20, None)
    ], "封流比 (涨停封单/流通)")

    # 双高: 隔夜≥20% + 开盘≥5%
    print("\n=== 双高: 隔夜≥20% + 开盘封单≥5% ===")
    dh = df_normal[(df_normal["yedan_pct"] >= 20) & (df_normal["open_seal_pct"] >= 5)]
    print(f"n={len(dh)}, 涨停率 {dh['is_zt'].mean()*100:.1f}%, 平均涨幅 {dh['chg_pct'].mean():.2f}%")

    # 三高: 上面 + 封流比≥5%
    th = dh[dh["fenglu_ratio"] >= 5]
    print(f"\n=== 三高: 双高 + 封流比≥5% ===")
    print(f"n={len(th)}, 涨停率 {th['is_zt'].mean()*100:.1f}%, 平均涨幅 {th['chg_pct'].mean():.2f}%")

if __name__ == "__main__":
    main()
