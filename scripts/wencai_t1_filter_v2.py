#!/usr/bin/env python3
"""
深挖极宝档 + 软封档 哪些条件下最强 / 应该过滤
- 单只票特征: 封流比, 首封时间细分, 是否一字板?
- 大盘维度: 已经做了 D 当日
- 板块?
"""
import warnings; warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd
import numpy as np

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
dates = sorted([f.stem.replace("preopen_","") for f in DATA.glob("preopen_*.csv")])

# 大盘
market = {}
for d in dates:
    df = pd.read_csv(DATA / f"prices3_{d}.csv", dtype={"股票代码":str})
    chg_col = None
    for c in df.columns:
        if "涨跌幅:前复权" in c and "排名" not in c: chg_col = c; break
    df["chg"] = pd.to_numeric(df[chg_col], errors="coerce")
    df = df.dropna(subset=["chg"])
    market[d] = {
        "mean_chg": df["chg"].mean(),
        "zt_n": len(df[df["chg"]>=9.5]),
    }

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
        elif "最高价:不复权" in c: rename[c] = "p_high"
        elif "最低价:不复权" in c: rename[c] = "p_low"
    px = px.rename(columns=rename)
    if "p_open" in px.columns and "p_close" in px.columns:
        for c in ["p_open","p_close","p_high","p_low"]:
            if c in px.columns:
                px[c] = pd.to_numeric(px[c], errors="coerce")
        all_px[d] = px.set_index("股票代码")

# 收集所有样本 (极宝 + 软封 + 硬中, 加多维特征)
rows = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    fl = all_fl[d]; px_now = all_px.get(d); px_next = all_px.get(d_next)
    if px_now is None or px_next is None: continue
    
    for _, row in fl.iterrows():
        code = str(row["股票代码"])
        if code not in px_now.index or code not in px_next.index: continue
        pb = px_now.at[code,"p_close"]; ps = px_next.at[code,"p_open"]
        if pd.isna(pb) or pd.isna(ps) or pb<=0 or ps<=0: continue
        # 一字板判断: D 最低 = 收盘 (基本一字)
        p_low = px_now.at[code,"p_low"] if "p_low" in px_now.columns else None
        is_yzb = (not pd.isna(p_low)) and abs(pb - p_low) / pb < 0.005
        
        rows.append({
            "date": d, "code": code,
            "fl": row["fenglu_ratio"], "fm": row["first_min"],
            "ret": (ps-pb)/pb*100,
            "is_yzb": is_yzb,
            "d_mkt_chg": market[d]["mean_chg"],
            "d_zt_n": market[d]["zt_n"],
        })

df = pd.DataFrame(rows)
print(f"全样本 {len(df)} 行 D 涨停股")

# 极宝档: 封流>=5 + 早封
bao = df[(df["fl"]>=5)&(df["fm"]>=540)&(df["fm"]<600)].copy()
soft = df[(df["fl"]>=3)&(df["fl"]<5)].copy()

print(f"\n极宝档 {len(bao)} 行")
print(f"  整体: 均 {bao['ret'].mean():.2f}%, 胜 {(bao['ret']>0).mean()*100:.0f}%")
print(f"\n--- 极宝档: 一字板 vs 非一字 ---")
for is_y, lbl in [(True,"一字板"),(False,"非一字")]:
    s = bao[bao["is_yzb"]==is_y]
    if len(s)<3: continue
    print(f"  {lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")

print(f"\n--- 极宝档: 9:30-9:35 (秒板) vs 9:35-10:00 (慢封) ---")
for lo, hi, lbl in [(540,545,"9:30-9:35 秒板"),(545,560,"9:35-9:40"),(560,580,"9:40-10:00")]:
    s = bao[(bao["fm"]>=lo)&(bao["fm"]<hi)]
    if len(s)<3: continue
    print(f"  {lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")

print(f"\n--- 极宝档: 封流比 5-7 vs 7-10 vs >10 ---")
for lo, hi, lbl in [(5,7,"5-7"),(7,10,"7-10"),(10,9999,">10")]:
    s = bao[(bao["fl"]>=lo)&(bao["fl"]<hi)]
    if len(s)<3: continue
    print(f"  封流{lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")

print(f"\n--- 极宝档: 当日涨停数过滤 ---")
for lo, hi, lbl in [(0,80,"涨停<80 (普通日)"),(80,200,"涨停80-200 (普通)"),(200,9999,"涨停>200 (大爆发)")]:
    s = bao[(bao["d_zt_n"]>=lo)&(bao["d_zt_n"]<hi)]
    if len(s)<3: continue
    print(f"  {lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")

# 排除一字板 (买不到)
print(f"\n=== 极宝档 排除一字板 (现实可买) ===")
real = bao[~bao["is_yzb"]]
print(f"n={len(real)}, 均 {real['ret'].mean():.2f}%, 胜 {(real['ret']>0).mean()*100:.0f}%")

# 软封档维度
print(f"\n\n软封档 {len(soft)} 行")
print(f"  整体: 均 {soft['ret'].mean():.2f}%, 胜 {(soft['ret']>0).mean()*100:.0f}%")
print(f"\n--- 软封: 一字板 vs 非一字 ---")
for is_y, lbl in [(True,"一字板"),(False,"非一字")]:
    s = soft[soft["is_yzb"]==is_y]
    if len(s)<3: continue
    print(f"  {lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")

print(f"\n--- 软封: 首封时间 ---")
for lo, hi, lbl in [(540,600,"早封 9:30-10:00"),(600,720,"上午 10:00-12:00"),(780,890,"下午 13:00-14:30"),(890,900,"尾盘14:30+")]:
    s = soft[(soft["fm"]>=lo)&(soft["fm"]<hi)]
    if len(s)<3: continue
    print(f"  {lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")

# 硬封中档为什么亏: 看是不是高位接力
print(f"\n\n硬封中档 (封流≥5 非早封) 深挖")
hard_mid = df[(df["fl"]>=5)&((df["fm"]<540)|(df["fm"]>=600))].copy()
print(f"n={len(hard_mid)}, 均 {hard_mid['ret'].mean():.2f}%, 胜 {(hard_mid['ret']>0).mean()*100:.0f}%")
for lo, hi, lbl in [(0,540,"早盘前 9:00 前"),(600,690,"10:00-11:30"),(780,840,"13:00-14:00"),(840,900,"14:00+ 尾盘")]:
    s = hard_mid[(hard_mid["fm"]>=lo)&(hard_mid["fm"]<hi)]
    if len(s)<3: continue
    print(f"  {lbl}: n={len(s)}, 均 {s['ret'].mean():.2f}%, 胜 {(s['ret']>0).mean()*100:.0f}%")
