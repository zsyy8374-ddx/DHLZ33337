#!/usr/bin/env python3
"""V3: 强制翻页, 拿全 5500+ 行"""
import warnings
warnings.filterwarnings('ignore')

import sys, time
from pathlib import Path
import pywencai
import pandas as pd

OUT = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def fetch(date_str, expected_min=5000, max_pages=60):
    """显式翻页, 直到拿到至少 expected_min 行"""
    query = f"{date_str} 收盘价 大于0 开盘价 涨跌幅 最高价 最低价 排名前6000"
    
    # 第一次用 loop=True 翻页
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    
    if df is None:
        return None
    
    if len(df) >= expected_min:
        return df
    
    # 不够, 手动翻页
    print(f"  loop 只拉到 {len(df)} 行, 手动续翻", flush=True)
    page_n = (len(df) // 100) + 1
    while page_n <= max_pages:
        try:
            extra = pywencai.get(query=query, page=page_n, perpage=100)
            if extra is None or len(extra) == 0:
                break
            df = pd.concat([df, extra], ignore_index=True)
            page_n += 1
            time.sleep(1.5)
        except Exception as e:
            print(f"  page {page_n} err: {e}")
            break
    
    df = df.drop_duplicates(subset=["股票代码"]) if "股票代码" in df.columns else df
    return df

def normalize(df, date_str):
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
        out = OUT / f"prices3_{day}.csv"
        if out.exists():
            cur = pd.read_csv(out)
            if len(cur) >= 5000:
                print(f"[skip] {day} ({len(cur)} 行)")
                continue
        print(f"[v3] {day}", flush=True)
        try:
            df = fetch(day)
            if df is not None:
                df = normalize(df, day)
                df.to_csv(out, index=False, encoding='utf-8-sig')
                print(f"  -> {len(df)} 行")
        except Exception as e:
            print(f"  err: {e}")
        time.sleep(3)

if __name__ == "__main__":
    main()
