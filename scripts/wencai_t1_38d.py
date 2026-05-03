#!/usr/bin/env python3
"""38 天 T+1 大样本验证 (3 月 + 4 月)"""
import warnings; warnings.filterwarnings('ignore')
from pathlib import Path
import pandas as pd

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")
# 拿到所有 fenglu + prices3 都齐的日期
fl_dates = set(f.stem.replace("fenglu_","") for f in DATA.glob("fenglu_*.csv"))
px_dates = set(f.stem.replace("prices3_","") for f in DATA.glob("prices3_*.csv"))
dates = sorted(fl_dates & px_dates)
print(f"齐全的交易日: {len(dates)} 天")
print(f"  {dates[:5]} ... {dates[-5:]}")

all_fl, all_px = {}, {}
for d in dates:
    fl = pd.read_csv(DATA / f"fenglu_{d}.csv", dtype={"code":str,"股票代码":str})
    if "fenglu_ratio" not in fl.columns: continue
    fl["fenglu_ratio"] = pd.to_numeric(fl["fenglu_ratio"], errors="coerce")
    def t2m(s):
        if pd.isna(s): return None
        try: return int(str(s).split(":")[0])*60+int(str(s).split(":")[1])
        except: return None
    if "zt_first_time" in fl.columns:
        fl["first_min"] = fl["zt_first_time"].apply(t2m)
    else:
        fl["first_min"] = None
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
            if c in px.columns: px[c] = pd.to_numeric(px[c], errors="coerce")
        all_px[d] = px.set_index("股票代码")

# 收集
rows = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    if d not in all_fl or d not in all_px or d_next not in all_px: continue
    fl = all_fl[d]; px_now = all_px[d]; px_next = all_px[d_next]
    
    for _, row in fl.iterrows():
        code = str(row["股票代码"])
        if code not in px_now.index or code not in px_next.index: continue
        pb = px_now.at[code,"p_close"]; ps = px_next.at[code,"p_open"]
        if pd.isna(pb) or pd.isna(ps) or pb<=0 or ps<=0: continue
        # 一字板
        ph = px_now.at[code,"p_high"] if "p_high" in px_now.columns else pb
        pl = px_now.at[code,"p_low"] if "p_low" in px_now.columns else pb
        po = px_now.at[code,"p_open"] if "p_open" in px_now.columns else pb
        is_yzb = (not pd.isna(ph)) and (not pd.isna(pl)) and (not pd.isna(po)) and \
                 abs(po-pb)/pb<0.005 and abs(ph-pl)/pb<0.005
        rows.append({
            "date":d,"code":code,"name":row["股票简称"],
            "fl":row["fenglu_ratio"],"fm":row["first_min"],
            "ret":(ps-pb)/pb*100, "is_yzb":is_yzb,
        })

df = pd.DataFrame(rows)
print(f"\n样本: {len(df)} 行 D 涨停股 (跨 {df['date'].nunique()} 天)")

real = df[~df["is_yzb"].fillna(False)]
print(f"非一字板: {len(real)} 行")
print(f"基线 T+1: 均 {real['ret'].mean():.2f}%, 胜率 {(real['ret']>0).mean()*100:.0f}%")

print("\n=== 38 天大样本各档位 (排除一字板) ===")
print(f"{'档位':<40} {'n':>5} {'均收益':>8} {'胜率':>6}")
for desc, mask in [
    ("软封+早封 (3-5 + 9:30-10:00)", (real["fl"]>=3)&(real["fl"]<5)&(real["fm"]>=540)&(real["fm"]<600)),
    ("软封 (3-5) 整体", (real["fl"]>=3)&(real["fl"]<5)),
    ("软封+10:00-12:00", (real["fl"]>=3)&(real["fl"]<5)&(real["fm"]>=600)&(real["fm"]<720)),
    ("封流2-3+早封", (real["fl"]>=2)&(real["fl"]<3)&(real["fm"]>=540)&(real["fm"]<600)),
    ("封流2-3 整体", (real["fl"]>=2)&(real["fl"]<3)),
    ("封流1-2", (real["fl"]>=1)&(real["fl"]<2)),
    ("封流<1", real["fl"]<1),
    ("极宝 (≥5+早封) 非一字 ⛔", (real["fl"]>=5)&(real["fm"]>=540)&(real["fm"]<600)),
    ("封流>10+早封 非一字 💀", (real["fl"]>=10)&(real["fm"]>=540)&(real["fm"]<600)),
    ("硬封中 (≥5 非早封) 非一字", (real["fl"]>=5)&((real["fm"]<540)|(real["fm"]>=600))),
]:
    s = real[mask.fillna(False)]
    if len(s)<5: 
        print(f"{desc:<40} {len(s):>5} (太少)")
        continue
    print(f"{desc:<40} {len(s):>5} {s['ret'].mean():>7.2f}% {(s['ret']>0).mean()*100:>5.0f}%")

# 按月对比
print("\n=== 3 月 vs 4 月 OOS 验证 ===")
real["month"] = real["date"].str[:6]
for m in sorted(real["month"].unique()):
    sub = real[real["month"]==m]
    gold = sub[(sub["fl"]>=3)&(sub["fl"]<5)&(sub["fm"]>=540)&(sub["fm"]<600)]
    print(f"  {m}: 总 {len(sub)} 行, 软封+早封 n={len(gold)}, 均 {gold['ret'].mean():.2f}%, 胜 {(gold['ret']>0).mean()*100:.0f}%")
