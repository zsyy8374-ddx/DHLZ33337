#!/usr/bin/env python3
"""拉 3 月数据扩大样本"""
import warnings
warnings.filterwarnings('ignore')

import sys, time
from pathlib import Path
import pywencai
import pandas as pd

OUT = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

# 3 月所有交易日 (周末/节假日除外)
MARCH = [
    "20260303","20260304","20260305","20260306","20260307",  # 这些可能没数据要试
]
# 全 3 月工作日
import datetime
def biz_days(start, end):
    d = datetime.date(*start)
    e = datetime.date(*end)
    out = []
    while d <= e:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d += datetime.timedelta(days=1)
    return out

# 3 月 + 4 月初 (节前)
days = biz_days((2026,3,3), (2026,3,31))
print(f"目标日: {days}")

def fetch_preopen_full(date_str):
    """拉 9:15 隔夜单 + 9:25 开盘封单"""
    query = (f"{date_str} 9点25分集合竞价 大于0 "
             f"分时成交额 排名前6000 上市时间 大于2024年")
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    return df

def fetch_fenglu_full(date_str):
    """拉涨停股 + 封流比 + 首封时间"""
    query = (f"{date_str} 涨停 排名前1500")
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    return df

def fetch_prices_full(date_str):
    """拉全 A 股价格"""
    query = f"{date_str} 收盘价 大于0 开盘价 涨跌幅 最高价 最低价 排名前6000"
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    return df

# 跳过已知问题日期 (添加到这里)
SKIP = {"20260306"}
# 先只拉价格 (T+1 回测最关键)
for day in days:
    if day in SKIP:
        print(f"[skip-known] {day}"); continue
    out = OUT / f"prices3_{day}.csv"
    if out.exists():
        cur = pd.read_csv(out)
        if len(cur) >= 5000:
            print(f"[skip] {day}")
            continue
    print(f"[march-px] {day}", flush=True)
    try:
        df = fetch_prices_full(day)
        if df is None or len(df)==0:
            print(f"  跳过 (无数据, 节假日?)")
            continue
        rename = {}
        for c in df.columns:
            if "开盘价:不复权" in c: rename[c] = "p_open"
            elif "收盘价:不复权" in c and "排名" not in c: rename[c] = "p_close"
            elif "最高价:不复权" in c: rename[c] = "p_high"
            elif "最低价:不复权" in c: rename[c] = "p_low"
            elif c == "最新涨跌幅": rename[c] = "chg_pct"
        df = df.rename(columns=rename)
        df["date"] = day
        df.to_csv(out, index=False, encoding='utf-8-sig')
        print(f"  -> {len(df)} 行")
    except Exception as e:
        print(f"  err: {e}")
    time.sleep(2)

print("价格数据拉完")
