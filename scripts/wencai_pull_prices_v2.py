#!/usr/bin/env python3
"""V2: 纯价格查询, 不带 9:25 条件"""
import warnings
warnings.filterwarnings('ignore')

import sys, time
from pathlib import Path
import pywencai
import pandas as pd

OUT = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def fetch(date_str, top_n=2000):
    query = (f"{date_str} 收盘价 大于0 开盘价 涨跌幅 最高价 最低价 排名前{top_n}")
    df = pywencai.get(query=query, loop=True)
    if df is None: return None
    rename = {}
    for c in df.columns:
        if "开盘价:不复权" in c:
            rename[c] = "p_open"
        elif "收盘价:不复权" in c and "排名" not in c:
            rename[c] = "p_close"
        elif "最高价:不复权" in c:
            rename[c] = "p_high"
        elif "最低价:不复权" in c:
            rename[c] = "p_low"
        elif c == "最新涨跌幅":
            rename[c] = "chg_pct"
    df = df.rename(columns=rename)
    df["date"] = date_str
    return df

def main():
    days = [
        "20260401","20260402","20260408","20260409","20260410",
        "20260411","20260414","20260415","20260416","20260417","20260418",
        "20260421","20260422","20260423","20260424","20260425",
        "20260428","20260429","20260430",
    ]
    if len(sys.argv) > 1:
        days = sys.argv[1:]

    for day in days:
        out = OUT / f"prices2_{day}.csv"
        if out.exists():
            print(f"[skip] {day}")
            continue
        print(f"[v2] {day}", flush=True)
        try:
            df = fetch(day)
            if df is not None:
                df.to_csv(out, index=False, encoding='utf-8-sig')
                # 检查关键列
                missing = [c for c in ["p_open","p_close"] if c not in df.columns]
                print(f"  -> {len(df)} 行, 缺列: {missing}")
        except Exception as e:
            print(f"  err: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()
