#!/usr/bin/env python3
"""
T+1 真实收益回测 (考虑 A股交易制度)

战法 A 真实模型:
- D 9:30 买入 (假设买入价 = D 开盘价)
- D 涨停封死, 不能卖
- D+1 9:30 卖出 (假设卖出价 = D+1 开盘价)
- 真实收益 = (D+1 开盘 - D 买入) / D 买入

战法 B 真实模型 (本来就是 T+1):
- D 14:55 买入 (假设买入价 = D 收盘价 = 涨停价)
- D+1 9:30 卖出 (D+1 开盘价)
- 真实收益 = (D+1 开盘 - D 收盘) / D 收盘
"""
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import numpy as np

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

dates = sorted([f.stem.replace("preopen_","") for f in DATA.glob("preopen_*.csv")])
print(f"交易日: {dates[0]} ~ {dates[-1]} ({len(dates)} 天)")

# 加载所有数据
all_po = {}    # 战法 A 信号
all_fl = {}    # 战法 B 信号 + 涨停股
all_px = {}    # 价格

for d in dates:
    po = pd.read_csv(DATA / f"preopen_{d}.csv", dtype={"code":str,"股票代码":str})
    for c in ["yedan_pct","open_seal_pct","chg_pct"]:
        po[c] = pd.to_numeric(po[c], errors="coerce")
    all_po[d] = po
    
    fl = pd.read_csv(DATA / f"fenglu_{d}.csv", dtype={"code":str,"股票代码":str})
    fl["fenglu_ratio"] = pd.to_numeric(fl["fenglu_ratio"], errors="coerce")
    # 首封时间 → 分钟
    def t2m(s):
        if pd.isna(s): return None
        parts = str(s).strip().split(":")
        if len(parts)<2: return None
        try: return int(parts[0])*60+int(parts[1])
        except: return None
    fl["first_min"] = fl["zt_first_time"].apply(t2m)
    all_fl[d] = fl
    
    px = pd.read_csv(DATA / f"prices3_{d}.csv", dtype={"code":str,"股票代码":str})
    # 4-1/4-2 没有 p_open/p_close, 用重权价 fallback
    if "p_open" not in px.columns:
        for c in px.columns:
            if "开盘价:前复权" in c and "09:25" not in c:
                px["p_open"] = pd.to_numeric(px[c], errors="coerce")
            elif "收盘价:前复权" in c:
                px["p_close"] = pd.to_numeric(px[c], errors="coerce")
    for c in ["p_925","p_open","p_close","chg_pct","p_high","p_low"]:
        if c in px.columns:
            px[c] = pd.to_numeric(px[c], errors="coerce")
    if "p_open" not in px.columns or "p_close" not in px.columns:
        print(f"  ⚠️ {d} 缺价格列, 跳过")
        continue
    all_px[d] = px.set_index("股票代码")

print(f"价格数据 (D+1 开盘卖出基准):")
print(f"  4-30: {len(all_px['20260430'])} 行")

# ========= 战法 A T+1 回测 =========
print("\n"+"="*70)
print("【战法 A T+1 真实回测】 D 开盘买 → D+1 开盘卖")
print("="*70)

results_a = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    po = all_po[d]
    px_now = all_px.get(d)
    px_next = all_px.get(d_next)
    if px_now is None or px_next is None: continue
    
    po = po[~po["股票简称"].astype(str).str.contains("ST", na=False)]
    
    for _, row in po.iterrows():
        code = str(row["股票代码"])
        if code not in px_now.index or code not in px_next.index: continue
        p_buy = px_now.at[code, "p_open"]  # D 开盘买
        if pd.isna(p_buy) or p_buy<=0: continue
        # D+1 开盘卖
        p_sell = px_next.at[code, "p_open"]
        if pd.isna(p_sell) or p_sell<=0: continue
        
        ret = (p_sell - p_buy) / p_buy * 100
        # 当日涨停判断
        d_chg = px_now.at[code, "chg_pct"]
        is_zt_d = d_chg >= 19 if code.startswith(("300","688","301")) else d_chg >= 9.5
        
        results_a.append({
            "date": d, "code": code, "name": row["股票简称"],
            "yedan_pct": row["yedan_pct"], "open_seal_pct": row["open_seal_pct"],
            "p_buy": p_buy, "p_sell": p_sell, "ret_pct": ret,
            "d_chg": d_chg, "d_is_zt": is_zt_d,
        })

ra = pd.DataFrame(results_a)
print(f"\n样本: {len(ra)} 行 (跨 {len(dates)-1} D→D+1, 排除 ST)")
print(f"基线 T+1 收益: 均值 {ra['ret_pct'].mean():.2f}%, 中位数 {ra['ret_pct'].median():.2f}%, 胜率 {(ra['ret_pct']>0).mean()*100:.1f}%")
print()

print("--- 战法 A 各档位 T+1 真实收益 ---")
print(f"{'档位':<35} {'n':>5} {'均收益':>8} {'中位':>8} {'胜率':>8} {'≥0%':>6}")
print("-"*75)

# 极强: 隔夜≥20% + 开盘≥5%
sub = ra[(ra["yedan_pct"]>=20)&(ra["open_seal_pct"]>=5)]
if len(sub)>0:
    print(f"{'极强 (隔夜≥20% + 开盘≥5%)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 强 1: 隔夜≥10% (单)
sub = ra[(ra["yedan_pct"]>=10)&(ra["open_seal_pct"]<5)]
if len(sub)>0:
    print(f"{'强1 (隔夜≥10%, 开盘<5%)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 强 2: 开盘≥3% (单)
sub = ra[(ra["yedan_pct"]<10)&(ra["open_seal_pct"]>=3)]
if len(sub)>0:
    print(f"{'强2 (开盘≥3%, 隔夜<10%)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 拾漏: 隔夜 1-10% + 开盘 0.1-3%
sub = ra[(ra["yedan_pct"]>=1)&(ra["yedan_pct"]<10)&(ra["open_seal_pct"]>=0.1)&(ra["open_seal_pct"]<3)]
if len(sub)>0:
    print(f"{'拾漏 (隔夜 1-10% + 开盘 0.1-3%)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 观察: 隔夜 5-10% + 开盘≈0
sub = ra[(ra["yedan_pct"]>=5)&(ra["yedan_pct"]<10)&(ra["open_seal_pct"]<0.1)]
if len(sub)>0:
    print(f"{'观察 (隔夜 5-10% + 开盘≈0)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 全市场 (基线)
print(f"{'全市场基线':<35} {len(ra):>5} {ra['ret_pct'].mean():>7.2f}% {ra['ret_pct'].median():>7.2f}% {(ra['ret_pct']>0).mean()*100:>7.1f}%")

# ========= 战法 B T+1 回测 =========
print("\n"+"="*70)
print("【战法 B T+1 真实回测】 D 14:55 买 (D 收盘价) → D+1 9:30 卖 (开盘价)")
print("="*70)

results_b = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    fl = all_fl[d]
    px_now = all_px.get(d)
    px_next = all_px.get(d_next)
    if px_now is None or px_next is None: continue
    
    fl = fl[~fl["股票简称"].astype(str).str.contains("ST", na=False)]
    
    for _, row in fl.iterrows():
        code = str(row["股票代码"])
        if code not in px_now.index or code not in px_next.index: continue
        p_buy = px_now.at[code, "p_close"]  # D 收盘价 (= 涨停价)
        if pd.isna(p_buy) or p_buy<=0: continue
        p_sell = px_next.at[code, "p_open"]  # D+1 开盘卖
        if pd.isna(p_sell) or p_sell<=0: continue
        
        ret = (p_sell - p_buy) / p_buy * 100
        results_b.append({
            "date": d, "code": code, "name": row["股票简称"],
            "fenglu_ratio": row["fenglu_ratio"], "first_min": row["first_min"],
            "p_buy": p_buy, "p_sell": p_sell, "ret_pct": ret,
        })

rb = pd.DataFrame(results_b)
print(f"\n样本: {len(rb)} 行 D 涨停股 (有 D+1 数据)")
print(f"基线 T+1 收益: 均值 {rb['ret_pct'].mean():.2f}%, 胜率 {(rb['ret_pct']>0).mean()*100:.1f}%")
print()

print(f"{'档位':<35} {'n':>5} {'均收益':>8} {'中位':>8} {'胜率':>8}")
print("-"*70)

# 极宝: 封流≥5 + 9:30-10:00
sub = rb[(rb["fenglu_ratio"]>=5)&(rb["first_min"]>=540)&(rb["first_min"]<600)]
if len(sub)>0:
    print(f"{'极宝 (封流≥5 + 9:30-10:00)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 硬封中: 封流≥5, 不是早封
sub = rb[(rb["fenglu_ratio"]>=5)&((rb["first_min"]<540)|(rb["first_min"]>=600))]
if len(sub)>0:
    print(f"{'硬封中 (封流≥5, 非早封)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 软封: 3-5
sub = rb[(rb["fenglu_ratio"]>=3)&(rb["fenglu_ratio"]<5)]
if len(sub)>0:
    print(f"{'软封 (封流 3-5)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

# 弱封: <3
sub = rb[rb["fenglu_ratio"]<3]
if len(sub)>0:
    print(f"{'弱封 (封流<3)':<35} {len(sub):>5} {sub['ret_pct'].mean():>7.2f}% {sub['ret_pct'].median():>7.2f}% {(sub['ret_pct']>0).mean()*100:>7.1f}%")

print(f"{'D 涨停股全部 (基线)':<35} {len(rb):>5} {rb['ret_pct'].mean():>7.2f}% {rb['ret_pct'].median():>7.2f}% {(rb['ret_pct']>0).mean()*100:>7.1f}%")
