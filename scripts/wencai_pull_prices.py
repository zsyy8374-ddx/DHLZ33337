#!/usr/bin/env python3
"""
拉每个交易日的 9:25 + 开盘 + 收盘价
用于 T+1 收益计算
"""
import warnings
warnings.filterwarnings('ignore')

import sys, time
from pathlib import Path
import pywencai
import pandas as pd

OUT_DIR = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def fetch_prices(date_str, top_n=1500):
    query = (f"{date_str} 9点25分集合竞价 大于0 "
             f"开盘价 收盘价 涨跌幅 排名前{top_n}")
    df = pywencai.get(query=query, loop=True)
    if df is None or len(df)==0: return None
    rename = {}
    for c in df.columns:
        # 9:25 撮合价
        if "分时收盘价" in c and "09:25" in c:
            rename[c] = "p_925"
        # 当日开盘
        elif "开盘价:不复权" in c and "09:25" not in c:
            rename[c] = "p_open"
        # 当日收盘
        elif "收盘价:不复权" in c:
            rename[c] = "p_close"
        elif "涨跌幅:前复权" in c and "排名" not in c:
            rename[c] = "chg_pct"
        elif "最高价:不复权" in c and "09:25" not in c:
            rename[c] = "p_high"
        elif "最低价:不复权" in c and "09:25" not in c:
            rename[c] = "p_low"
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
        out = OUT_DIR / f"prices_{day}.csv"
        if out.exists():
            print(f"[skip] {day}")
            continue
        print(f"[prices] {day}", flush=True)
        try:
            df = fetch_prices(day)
            if df is not None:
                df.to_csv(out, index=False, encoding='utf-8-sig')
                print(f"  -> {len(df)} 行")
        except Exception as e:
            print(f"  err: {e}")
        time.sleep(2)

if __name__ == "__main__":
    main()
