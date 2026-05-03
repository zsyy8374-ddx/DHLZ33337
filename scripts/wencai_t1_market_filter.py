#!/usr/bin/env python3
"""
分析: 大盘强弱与极宝档收益的关系
- D 当日全市场均涨幅 vs 极宝档 D+1 收益
- D+1 全市场均涨幅 (后视) vs 极宝档收益
- 看能否用 D 当日数据预测次日开盘
"""
import warnings; warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd
import numpy as np

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
dates = sorted([f.stem.replace("preopen_","") for f in DATA.glob("preopen_*.csv")])

# 各天大盘指标
market = {}
for d in dates:
    df = pd.read_csv(DATA / f"prices3_{d}.csv", dtype={"股票代码":str})
    chg_col = None
    for c in df.columns:
        if "涨跌幅:前复权" in c and "排名" not in c: chg_col = c; break
    if chg_col is None:
        for c in df.columns:
            if "最新涨跌幅" in c: chg_col = c; break
    df["chg"] = pd.to_numeric(df[chg_col], errors="coerce")
    df = df.dropna(subset=["chg"])
    market[d] = {
        "mean_chg": df["chg"].mean(),
        "red_pct": (df["chg"]>0).mean()*100,
        "zt_n": len(df[df["chg"]>=9.5]),
        "stock_n": len(df),
    }

# 加载战法 B 数据
all_fl, all_px = {}, {}
for d in dates:
    fl = pd.read_csv(DATA / f"fenglu_{d}.csv", dtype={"code":str,"股票代码":str})
    fl["fenglu_ratio"] = pd.to_numeric(fl["fenglu_ratio"], errors="coerce")
    def t2m(s):
        if pd.isna(s): return None
        try: return int(str(s).split(":")[0])*60+int(str(s).split(":")[1])
        except: return None
    fl["first_min"] = fl["zt_first_time"].apply(t2m)
    all_fl[d] = fl[~fl["股票简称"].astype(str).str.contains("ST", na=False)]
    px = pd.read_csv(DATA / f"prices3_{d}.csv", dtype={"code":str,"股票代码":str})
    rename = {}
    for c in px.columns:
        if "开盘价:不复权" in c: rename[c] = "p_open"
        elif "收盘价:不复权" in c and "排名" not in c: rename[c] = "p_close"
    px = px.rename(columns=rename)
    if "p_open" in px.columns and "p_close" in px.columns:
        for c in ["p_open","p_close"]: px[c] = pd.to_numeric(px[c], errors="coerce")
        all_px[d] = px.set_index("股票代码")

# 收集每日极宝档样本 + 当日大盘 + 次日开盘
rows = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    fl = all_fl[d]; px_now = all_px.get(d); px_next = all_px.get(d_next)
    if px_now is None or px_next is None: continue
    
    bao = fl[(fl["fenglu_ratio"]>=5)&(fl["first_min"]>=540)&(fl["first_min"]<600)]
    for _, row in bao.iterrows():
        code = str(row["股票代码"])
        if code not in px_now.index or code not in px_next.index: continue
        pb = px_now.at[code,"p_close"]; ps = px_next.at[code,"p_open"]
        if pd.isna(pb) or pd.isna(ps) or pb<=0 or ps<=0: continue
        rows.append({
            "date": d, "code": code,
            "ret": (ps-pb)/pb*100,
            "d_market_chg": market[d]["mean_chg"],
            "d_red_pct": market[d]["red_pct"],
            "d_zt_n": market[d]["zt_n"],
            "fl": row["fenglu_ratio"],
            "fm": row["first_min"],
        })

df = pd.DataFrame(rows)
print(f"极宝档样本: {len(df)} 行 (跨 {df['date'].nunique()} 天)")
print(f"整体均收益: {df['ret'].mean():.2f}%")

print("\n--- 按 D 当日大盘均涨 分桶 ---")
for lo, hi, lbl in [(-99, -0.5, "弱 (<-0.5%)"), (-0.5, 0.3, "中 (-0.5~0.3%)"), 
                   (0.3, 1.0, "中强 (0.3-1%)"), (1.0, 99, "强 (>1%)")]:
    sub = df[(df["d_market_chg"]>=lo)&(df["d_market_chg"]<hi)]
    if len(sub)<3: continue
    print(f"  {lbl}: n={len(sub)}, 均收益 {sub['ret'].mean():.2f}%, 胜率 {(sub['ret']>0).mean()*100:.0f}%")

print("\n--- 按 D 当日红盘比 分桶 ---")
for lo, hi, lbl in [(0,40,"红盘<40%"),(40,60,"红盘40-60%"),(60,80,"红盘60-80%"),(80,100,"红盘>80%")]:
    sub = df[(df["d_red_pct"]>=lo)&(df["d_red_pct"]<hi)]
    if len(sub)<3: continue
    print(f"  {lbl}: n={len(sub)}, 均收益 {sub['ret'].mean():.2f}%, 胜率 {(sub['ret']>0).mean()*100:.0f}%")

print("\n--- 按 D 当日涨停数 分桶 ---")
for lo, hi, lbl in [(0,80,"<80"),(80,120,"80-120"),(120,200,"120-200"),(200,9999,">200")]:
    sub = df[(df["d_zt_n"]>=lo)&(df["d_zt_n"]<hi)]
    if len(sub)<3: continue
    print(f"  涨停{lbl}: n={len(sub)}, 均收益 {sub['ret'].mean():.2f}%, 胜率 {(sub['ret']>0).mean()*100:.0f}%")

print("\n--- 双条件: D 大盘强 & 涨停多 ---")
strong = df[(df["d_market_chg"]>=0.3)&(df["d_zt_n"]>=80)]
weak = df[(df["d_market_chg"]<0.3)|(df["d_zt_n"]<80)]
print(f"  强势 (大盘≥0.3% 且 涨停≥80): n={len(strong)}, 均收益 {strong['ret'].mean():.2f}%, 胜率 {(strong['ret']>0).mean()*100:.0f}%")
print(f"  弱势 (大盘<0.3% 或 涨停<80): n={len(weak)}, 均收益 {weak['ret'].mean():.2f}%, 胜率 {(weak['ret']>0).mean()*100:.0f}%")
