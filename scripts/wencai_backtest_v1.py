#!/usr/bin/env python3
"""
4 月 19 天大样本回测: 验证 Dengxian 5-3 教的 3 公式预测力

数据源:
- preopen_*.csv: 全市场 (按 9:15 买二>0 筛) ~117 行/天
- fenglu_*.csv: 涨停股 + 涨停时间 + 开板次数 ~70-100 行/天

研究问题:
1. 隔夜单占比 → 当日涨停率 (大样本)
2. 开盘封单占比 → 当日涨停率
3. 双高 (隔夜≥X + 开盘≥Y) 命中率分组
4. 涨停时间 → 次日表现 (待 D+1 数据)
5. 炸板次数 → 封板硬度
6. 板块强度 v0.2: 首封均值 + 炸板率 + 封流比
"""
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import numpy as np
import re
from collections import defaultdict

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

def load_preopen():
    """全市场盘前数据"""
    dfs = []
    for f in sorted(DATA.glob("preopen_*.csv")):
        df = pd.read_csv(f, dtype={"code": str, "股票代码": str})
        df["date"] = f.stem.replace("preopen_", "")
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

def load_fenglu():
    """涨停股 + 时间数据"""
    dfs = []
    for f in sorted(DATA.glob("fenglu_*.csv")):
        df = pd.read_csv(f, dtype={"code": str, "股票代码": str})
        date = f.stem.replace("fenglu_", "")
        df["date"] = date
        # 时间字段重命名 (可能没标准化)
        for c in df.columns:
            if "首次涨停时间" in c:
                df = df.rename(columns={c: "zt_first_time"})
            elif "最后涨停时间" in c or "最终涨停时间" in c:
                df = df.rename(columns={c: "zt_last_time"})
            elif "涨停开板次数" in c:
                df = df.rename(columns={c: "kaiban"})
            elif "涨停原因类别" in c:
                df = df.rename(columns={c: "concepts"})
            elif "涨停封单额" in c and "fenglu" not in c.lower():
                df = df.rename(columns={c: "fengdan_e"})
        dfs.append(df)
    return pd.concat(dfs, ignore_index=True)

def is_zt(chg, name="", code=""):
    if pd.isna(chg):
        return False
    if "ST" in str(name):
        return chg >= 4.5
    if str(code).startswith(("300", "688", "301")):
        return chg >= 19.0
    return chg >= 9.5

def t2min(s):
    if pd.isna(s):
        return None
    parts = str(s).strip().split(":")
    if len(parts) < 2:
        return None
    try:
        return int(parts[0])*60 + int(parts[1])
    except:
        return None

def m2t(m):
    if pd.isna(m):
        return ''
    h, mi = divmod(int(m), 60)
    return f"{h:02d}:{mi:02d}"

# ===== 1. preopen: 隔夜单 + 开盘封单 =====
print("="*70)
print("【1】 大样本回测: 9:15 隔夜单 + 9:25 开盘封单 (Dengxian 5-3 教)")
print("="*70)

po = load_preopen()
print(f"\n样本: {len(po)} 行 ({po['date'].nunique()} 天)")

for c in ["yedan_pct", "open_seal_pct", "chg_pct"]:
    po[c] = pd.to_numeric(po[c], errors="coerce")

po["is_zt"] = po.apply(lambda r: is_zt(r["chg_pct"], r.get("股票简称", ""), r.get("code", "")), axis=1)

# 排除 ST (噪声大)
po_n = po[~po["股票简称"].astype(str).str.contains("ST", na=False)].copy()
print(f"排除 ST 后: {len(po_n)} 行, 整体涨停率 {po_n['is_zt'].mean()*100:.1f}%")

# 1.1 隔夜单占比分桶
print("\n--- 隔夜单占比 (9:15 买二/流通) ---")
print(f"{'区间':<12} {'n':>5} {'涨停率':>8} {'平均涨幅':>10} {'lift':>6}")
print("-"*50)
base = po_n["is_zt"].mean()
for lo, hi in [(0,1),(1,3),(3,5),(5,10),(10,20),(20,50),(50,100),(100,9999)]:
    sub = po_n[(po_n["yedan_pct"]>=lo)&(po_n["yedan_pct"]<hi)]
    if len(sub)==0: continue
    rate = sub["is_zt"].mean()
    print(f"{lo}-{hi}%{'':<6} {len(sub):>5} {rate*100:>7.1f}% {sub['chg_pct'].mean():>9.2f}% {rate/base:>6.2f}x")

# 1.2 开盘封单占比
print("\n--- 开盘封单占比 (9:25 买一/流通) ---")
print(f"{'区间':<12} {'n':>5} {'涨停率':>8} {'平均涨幅':>10} {'lift':>6}")
print("-"*50)
for lo, hi in [(0,0.1),(0.1,1),(1,3),(3,5),(5,10),(10,20),(20,9999)]:
    sub = po_n[(po_n["open_seal_pct"]>=lo)&(po_n["open_seal_pct"]<hi)]
    if len(sub)==0: continue
    rate = sub["is_zt"].mean()
    print(f"{lo}-{hi}%{'':<6} {len(sub):>5} {rate*100:>7.1f}% {sub['chg_pct'].mean():>9.2f}% {rate/base:>6.2f}x")

# 1.3 双高
print("\n--- 双高 (隔夜≥X% + 开盘≥Y%) ---")
print(f"{'阈值':<20} {'n':>5} {'涨停率':>8} {'lift':>6}")
print("-"*50)
for x, y in [(5,1),(10,1),(10,3),(20,3),(20,5),(30,5),(50,5)]:
    sub = po_n[(po_n["yedan_pct"]>=x)&(po_n["open_seal_pct"]>=y)]
    if len(sub)==0:
        print(f"≥{x}%, ≥{y}%{'':<8} {0:>5}     —")
        continue
    rate = sub["is_zt"].mean()
    print(f"≥{x}%, ≥{y}%{'':<8} {len(sub):>5} {rate*100:>7.1f}% {rate/base:>6.2f}x")

# ===== 2. fenglu: 涨停股的封板时间和炸板 =====
print("\n" + "="*70)
print("【2】 涨停股封板硬度 (首封时间 + 炸板次数 + 封流比)")
print("="*70)

fl = load_fenglu()
print(f"\n样本: {len(fl)} 行 (4 月所有涨停股)")

for c in ["fenglu_ratio"]:
    fl[c] = pd.to_numeric(fl[c], errors="coerce")
fl["kaiban"] = pd.to_numeric(fl["kaiban"], errors="coerce").fillna(0).astype(int)
fl["first_min"] = fl["zt_first_time"].apply(t2min)
fl["last_min"] = fl["zt_last_time"].apply(t2min)
fl["hold_min"] = fl["last_min"] - fl["first_min"]

print(f"\n炸板分布:")
for n in range(0, 5):
    if n == 4:
        cnt = (fl["kaiban"]>=4).sum()
        print(f"  ≥4 次: {cnt} ({cnt/len(fl)*100:.1f}%)")
    else:
        cnt = (fl["kaiban"]==n).sum()
        print(f"  {n} 次: {cnt} ({cnt/len(fl)*100:.1f}%)")

print(f"\n首封时间分布:")
for lo, hi, label in [(540, 570, "9:00-9:30 (集合)"),
                      (570, 600, "9:30-10:00"),
                      (600, 660, "10:00-11:00"),
                      (660, 690, "11:00-11:30"),
                      (780, 840, "13:00-14:00"),
                      (840, 900, "14:00-15:00")]:
    cnt = ((fl["first_min"]>=lo)&(fl["first_min"]<hi)).sum()
    print(f"  {label}: {cnt} ({cnt/len(fl)*100:.1f}%)")

# 首封时间 vs 炸板次数
print(f"\n首封时间 vs 平均炸板次数 (越早封越稳吗?):")
print(f"{'时段':<20} {'n':>5} {'平均炸板次数':>10} {'0炸板比例':>10}")
print("-"*55)
for lo, hi, label in [(540, 600, "9:00-10:00"),
                      (600, 660, "10:00-11:00"),
                      (660, 690, "11:00-11:30"),
                      (780, 840, "13:00-14:00"),
                      (840, 900, "14:00+")]:
    sub = fl[(fl["first_min"]>=lo)&(fl["first_min"]<hi)]
    if len(sub)==0: continue
    print(f"{label:<20} {len(sub):>5} {sub['kaiban'].mean():>10.2f} {(sub['kaiban']==0).mean()*100:>9.1f}%")

# 封流比 vs 炸板
print(f"\n封流比 vs 炸板次数 (封单大就稳吗?):")
print(f"{'封流比':<12} {'n':>5} {'平均炸板':>10} {'0炸板比例':>10}")
print("-"*45)
for lo, hi in [(0,0.5),(0.5,1),(1,3),(3,5),(5,10),(10,9999)]:
    sub = fl[(fl["fenglu_ratio"]>=lo)&(fl["fenglu_ratio"]<hi)]
    if len(sub)==0: continue
    print(f"{lo}-{hi}{'':<6} {len(sub):>5} {sub['kaiban'].mean():>10.2f} {(sub['kaiban']==0).mean()*100:>9.1f}%")
