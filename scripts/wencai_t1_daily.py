#!/usr/bin/env python3
"""
按日拆解战法 B 各档位 T+1 收益, 看稳定性
- 极宝档每天命中率分布
- 是否有少数天数撑起整个 +3.36%
- 多日 lift 是否稳定
"""
import warnings
warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd
import numpy as np

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
dates = sorted([f.stem.replace("preopen_","") for f in DATA.glob("preopen_*.csv")])
print(f"交易日 {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")

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
        for c in ["p_open","p_close"]:
            px[c] = pd.to_numeric(px[c], errors="coerce")
        all_px[d] = px.set_index("股票代码")

# 按日拆战法 B
print("\n"+"="*80)
print("【战法 B】每日各档位真实 T+1 收益分布")
print("="*80)
print(f"{'日期':<10} {'极宝n':>6} {'极宝均':>8} {'胜率':>6}|{'软封n':>6} {'软封均':>8} {'胜率':>6}|{'硬中n':>6} {'硬中均':>8}")
print("-"*80)

daily_stats = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    fl = all_fl[d]
    px_now = all_px.get(d); px_next = all_px.get(d_next)
    if px_now is None or px_next is None: continue
    
    rows = []
    for _, row in fl.iterrows():
        code = str(row["股票代码"])
        if code not in px_now.index or code not in px_next.index: continue
        pb = px_now.at[code, "p_close"]; ps = px_next.at[code, "p_open"]
        if pd.isna(pb) or pd.isna(ps) or pb<=0 or ps<=0: continue
        rows.append({"code":code,"fl":row["fenglu_ratio"],"fm":row["first_min"],"ret":(ps-pb)/pb*100})
    df = pd.DataFrame(rows)
    if len(df)==0: continue
    
    bao = df[(df["fl"]>=5)&(df["fm"]>=540)&(df["fm"]<600)]
    soft = df[(df["fl"]>=3)&(df["fl"]<5)]
    hard_mid = df[(df["fl"]>=5)&((df["fm"]<540)|(df["fm"]>=600))]
    
    def fmt(s):
        if len(s)==0: return ("--", "--", "--")
        return (len(s), f"{s['ret'].mean():.2f}%", f"{(s['ret']>0).mean()*100:.0f}%")
    
    b1 = fmt(bao); b2 = fmt(soft); b3 = fmt(hard_mid)
    print(f"{d:<10} {b1[0]:>6} {b1[1]:>8} {b1[2]:>6}|{b2[0]:>6} {b2[1]:>8} {b2[2]:>6}|{b3[0]:>6} {b3[1]:>8}")
    daily_stats.append({"date":d, "bao_n":len(bao),"bao_ret":bao["ret"].mean() if len(bao)>0 else None,
                       "soft_n":len(soft),"soft_ret":soft["ret"].mean() if len(soft)>0 else None})

# 稳定性分析
ds = pd.DataFrame(daily_stats)
print(f"\n--- 极宝档跨日稳定性 ---")
ds_b = ds.dropna(subset=["bao_ret"])
print(f"有极宝档的天数: {len(ds_b)}/{len(ds)}")
print(f"日均收益: 均 {ds_b['bao_ret'].mean():.2f}%, 中 {ds_b['bao_ret'].median():.2f}%, std {ds_b['bao_ret'].std():.2f}%")
print(f"正收益天数: {(ds_b['bao_ret']>0).sum()}/{len(ds_b)} = {(ds_b['bao_ret']>0).mean()*100:.0f}%")
print(f"亏损天数: {(ds_b['bao_ret']<0).sum()} / 大于 -2%: {(ds_b['bao_ret']<-2).sum()}")

print(f"\n--- 软封档跨日稳定性 ---")
ds_s = ds.dropna(subset=["soft_ret"])
print(f"有软封档的天数: {len(ds_s)}/{len(ds)}")
print(f"日均收益: 均 {ds_s['soft_ret'].mean():.2f}%, 中 {ds_s['soft_ret'].median():.2f}%, std {ds_s['soft_ret'].std():.2f}%")
print(f"正收益天数: {(ds_s['soft_ret']>0).sum()}/{len(ds_s)}")
