#!/usr/bin/env python3
"""
分两个查询拉问财数据:
1. 隔夜+开盘 (全市场) -> data/wencai/preopen_YYYYMMDD.csv
2. 封流比 (涨停股) -> data/wencai/fenglu_YYYYMMDD.csv

Dengxian 5-3 教的公式:
- 9:15 买二*100/自由流通股 = 隔夜单占比
- 9:25 买一*100/自由流通股 = 开盘封单占比
- 涨停封单量*100/自由流通股 = 封流比
"""
import warnings
warnings.filterwarnings('ignore')

import os, sys, time
from pathlib import Path
import pandas as pd
import pywencai

OUT_DIR = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
OUT_DIR.mkdir(parents=True, exist_ok=True)

def fetch_preopen(date_str, top_n=500):
    """全市场前 N 只 (按 9:15 买二/流通 排序), 不限涨停"""
    query = (f"{date_str} 9点15分买二*100/自由流通股 大于0 "
             f"9点25分买一*100/自由流通股 "
             f"涨跌幅 涨停 排名前{top_n}")
    df = pywencai.get(query=query, loop=True)
    if df is None or len(df) == 0:
        return None
    rename_map = {}
    for col in df.columns:
        if "分时买二量" in col and "/" in col and "自由流通股" in col:
            rename_map[col] = "yedan_pct"
        elif "分时买一量" in col and "/" in col and "自由流通股" in col:
            rename_map[col] = "open_seal_pct"
        elif "实际换手率" in col:
            rename_map[col] = "real_turnover"
        elif "自由流通市值" in col:
            rename_map[col] = "free_mkt_cap"
        elif col == "最新涨跌幅":
            rename_map[col] = "chg_pct"
    df = df.rename(columns=rename_map)
    df["date"] = date_str
    return df

def fetch_fenglu(date_str, top_n=500):
    """涨停股的封流比 (只对涨停有意义)"""
    query = (f"{date_str} 涨停封单量*100/自由流通股 大于0 "
             f"涨停时间 涨停原因 排名前{top_n}")
    df = pywencai.get(query=query, loop=True)
    if df is None or len(df) == 0:
        return None
    rename_map = {}
    for col in df.columns:
        if "涨停封单量" in col and "/" in col and "自由流通股" in col:
            rename_map[col] = "fenglu_ratio"
        elif "首次涨停时间" in col:
            rename_map[col] = "zt_first_time"
        elif "最终涨停时间" in col or "最后涨停时间" in col:
            rename_map[col] = "zt_last_time"
    df = df.rename(columns=rename_map)
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
        po_out = OUT_DIR / f"preopen_{day}.csv"
        fl_out = OUT_DIR / f"fenglu_{day}.csv"
        if po_out.exists() and fl_out.exists():
            print(f"[skip] {day}")
            continue

        if not po_out.exists():
            print(f"[preopen] {day} ...", flush=True)
            try:
                df = fetch_preopen(day)
                if df is not None:
                    df.to_csv(po_out, index=False, encoding='utf-8-sig')
                    print(f"  -> {len(df)} 行")
                else:
                    print(f"  -> 无")
            except Exception as e:
                print(f"  err: {e}")
            time.sleep(2)

        if not fl_out.exists():
            print(f"[fenglu] {day} ...", flush=True)
            try:
                df = fetch_fenglu(day)
                if df is not None:
                    df.to_csv(fl_out, index=False, encoding='utf-8-sig')
                    print(f"  -> {len(df)} 行")
                else:
                    print(f"  -> 无")
            except Exception as e:
                print(f"  err: {e}")
            time.sleep(2)

if __name__ == "__main__":
    main()
