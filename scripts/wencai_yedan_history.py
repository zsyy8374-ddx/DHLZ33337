#!/usr/bin/env python3
"""
拉取问财历史数据: 9:15 买二 + 9:25 买一 + 涨停封单 (三件套)
Dengxian 5-3 教的公式组合, 加日期前缀就能查历史.

输出: data/wencai/yedan_YYYYMMDD.parquet
"""
import warnings
warnings.filterwarnings('ignore')

import os, sys, time
from pathlib import Path
import pandas as pd
import pywencai

OUT_DIR = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
OUT_DIR.mkdir(parents=True, exist_ok=True)

USE_PARQUET = False  # set True if pyarrow installed

def fetch_one_day(date_str, top_n=300):
    """date_str: YYYYMMDD"""
    # "大于0" 是必要的过滤条件, 避免问财默认只返回涨停股
    query = (f"{date_str} 9点15分买二*100/自由流通股 大于0 "
             f"9点25分买一*100/自由流通股 "
             f"涨停封单量*100/自由流通股 "
             f"涨跌幅 排名前{top_n}")
    df = pywencai.get(query=query, loop=True)
    if df is None or len(df) == 0:
        return None
    # 标准化列名: 找到关键比值列, 重命名
    rename_map = {}
    for col in df.columns:
        if "分时买二量" in col and "/" in col and "自由流通股" in col:
            rename_map[col] = "yedan_pct"  # 隔夜单占比
        elif "分时买一量" in col and "/" in col and "自由流通股" in col:
            rename_map[col] = "open_seal_pct"  # 开盘封单占比
        elif "涨停封单量" in col and "/" in col and "自由流通股" in col:
            rename_map[col] = "fenglu_ratio"  # 封流比
        elif "分时涨跌幅" in col and "09:25" in col and "排名" not in col:
            rename_map[col] = "auction_chg_pct"  # 9:25 集合竞价涨跌幅
        elif "实际换手率" in col:
            rename_map[col] = "real_turnover"
        elif "自由流通市值" in col:
            rename_map[col] = "free_mkt_cap"
        elif col == "最新涨跌幅":
            rename_map[col] = "chg_pct"  # 当日收盘涨跌幅
    df = df.rename(columns=rename_map)
    df["date"] = date_str
    return df

def fetch_one_day_old(date_str, top_n=300):
    pass

def main():
    # 4 月所有交易日 (排除清明 4-3~4-7, 五一 4-29, 5-1~5-3)
    trade_days = [
        "20260401","20260402","20260408","20260409","20260410",
        "20260411","20260414","20260415","20260416","20260417","20260418",
        "20260421","20260422","20260423","20260424","20260425",
        "20260428","20260429","20260430",
    ]
    if len(sys.argv) > 1:
        trade_days = sys.argv[1:]

    ext = "parquet" if USE_PARQUET else "csv"
    for day in trade_days:
        out = OUT_DIR / f"yedan_{day}.{ext}"
        if out.exists():
            print(f"[skip] {day} 已存在")
            continue
        print(f"[fetch] {day} ...", flush=True)
        try:
            df = fetch_one_day(day)
            if df is None:
                print(f"  -> 无数据")
                continue
            if USE_PARQUET:
                df.to_parquet(out, index=False)
            else:
                df.to_csv(out, index=False, encoding='utf-8-sig')
            print(f"  -> {len(df)} 行 已保存")
        except Exception as e:
            print(f"  -> 错误: {e}")
        time.sleep(2)  # 客气点, 不爆问财

if __name__ == "__main__":
    main()
