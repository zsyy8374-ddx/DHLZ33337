#!/usr/bin/env python3
"""拉 3 月涨停股 (fenglu_*.csv) 数据"""
import warnings
warnings.filterwarnings('ignore')

import sys, time
from pathlib import Path
import pywencai
import pandas as pd
import datetime

OUT = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def biz_days(start, end):
    d = datetime.date(*start)
    e = datetime.date(*end)
    out = []
    while d <= e:
        if d.weekday() < 5: out.append(d.strftime("%Y%m%d"))
        d += datetime.timedelta(days=1)
    return out

SKIP = {"20260306"}

def fetch_zt(date_str):
    """拉涨停股 + 封单 + 流通市值 + 首封时间"""
    query = (f"{date_str} 涨停 封单金额 流通市值 涨停封板时间 "
             f"开盘价 收盘价 最高价 最低价 排名前1500")
    df = pywencai.get(query=query, loop=True, perpage=100, sleep=1)
    if df is None: return None
    rename = {}
    for c in df.columns:
        cs = str(c)
        if ("封单金额" in cs or "涨停封单额" in cs) and "排名" not in cs: rename[c] = "feng_dan_jin"
        elif "封单量" in cs and "金额" not in cs: rename[c] = "feng_dan_liang"
        elif ("流通市值" in cs or "a股市值" in cs) and "封单" not in cs and "比" not in cs: rename[c] = "ltsz"
        elif "首次涨停时间" in cs or "首次封板时间" in cs or ("涨停封板时长" not in cs and "涨停开板次数" not in cs and ("封板时间" in cs or "涨停封单时间" in cs)): rename[c] = "zt_first_time"
        elif "开盘价:不复权" in cs: rename[c] = "p_open"
        elif "收盘价:不复权" in cs and "排名" not in cs: rename[c] = "p_close"
        elif "最高价:不复权" in cs: rename[c] = "p_high"
        elif "最低价:不复权" in cs: rename[c] = "p_low"
        elif "涨跌幅:前复权" in cs and "排名" not in cs: rename[c] = "chg_pct"
    df = df.rename(columns=rename)
    # 计算封流比
    if "feng_dan_jin" in df.columns and "ltsz" in df.columns:
        df["feng_dan_jin"] = pd.to_numeric(df["feng_dan_jin"], errors="coerce")
        df["ltsz"] = pd.to_numeric(df["ltsz"], errors="coerce")
        df["fenglu_ratio"] = df["feng_dan_jin"] / df["ltsz"] * 100
    df["date"] = date_str
    return df

days = biz_days((2026,3,3), (2026,3,31))

for day in days:
    if day in SKIP:
        print(f"[skip-known] {day}"); continue
    out = OUT / f"fenglu_{day}.csv"
    if out.exists():
        cur = pd.read_csv(out)
        if "fenglu_ratio" in cur.columns and len(cur) > 0:
            print(f"[skip] {day} ({len(cur)} 行)"); continue
    print(f"[zt] {day}", flush=True)
    try:
        df = fetch_zt(day)
        if df is None or len(df)==0:
            print(f"  无数据"); continue
        df.to_csv(out, index=False, encoding='utf-8-sig')
        n_with_fl = df["fenglu_ratio"].notna().sum() if "fenglu_ratio" in df.columns else 0
        print(f"  -> {len(df)} 行, {n_with_fl} 行有封流比")
    except Exception as e:
        print(f"  err: {e}")
    time.sleep(2)

print("3 月涨停股拉完")
