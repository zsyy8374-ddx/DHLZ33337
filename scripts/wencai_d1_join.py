#!/usr/bin/env python3
"""
D+1 表现 join:
- preopen[D] 里的票 → fenglu[D+1] 看次日是不是涨停
- 验证 D 当日 9:15+9:25 信号 → D+1 涨停的预测力
- 涨停封流比[D] → D+1 是否再封 (反包率)
"""
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import numpy as np

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

dates = sorted([f.stem.replace("preopen_","") for f in DATA.glob("preopen_*.csv")])
print(f"交易日: {dates}\n")

# 加载所有 preopen
all_po = {}
for d in dates:
    df = pd.read_csv(DATA / f"preopen_{d}.csv", dtype={"code":str, "股票代码":str})
    for c in ["yedan_pct","open_seal_pct","chg_pct"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    all_po[d] = df

# 加载所有 fenglu
all_fl = {}
for d in dates:
    df = pd.read_csv(DATA / f"fenglu_{d}.csv", dtype={"code":str,"股票代码":str})
    df["fenglu_ratio"] = pd.to_numeric(df["fenglu_ratio"], errors="coerce")
    all_fl[d] = df

# join: 对每个 D 的 preopen, 看 D+1 的 fenglu
print("="*70)
print("【D+1 涨停验证】 D 日的 preopen 信号 → D+1 是否涨停")
print("="*70)

joined = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    po = all_po[d].copy()
    fl_next = all_fl[d_next]
    zt_codes_next = set(fl_next["股票代码"].astype(str).tolist())
    po["next_zt"] = po["股票代码"].astype(str).isin(zt_codes_next)
    po["d"] = d
    po["d_next"] = d_next
    joined.append(po)

J = pd.concat(joined, ignore_index=True)
J = J[~J["股票简称"].astype(str).str.contains("ST", na=False)]
print(f"样本: {len(J)} 行 (跨 {len(dates)-1} 天 D→D+1)")
print(f"D+1 涨停率基线: {J['next_zt'].mean()*100:.1f}%")

# D 日隔夜单 → D+1 涨停
print("\n--- D 日隔夜单占比 → D+1 涨停率 ---")
print(f"{'区间':<15} {'n':>5} {'D+1涨停率':>10} {'lift':>6}")
print("-"*45)
base = J["next_zt"].mean()
for lo, hi in [(0,1),(1,5),(5,10),(10,20),(20,50),(50,9999)]:
    sub = J[(J["yedan_pct"]>=lo)&(J["yedan_pct"]<hi)]
    if len(sub)==0: continue
    rate = sub["next_zt"].mean()
    print(f"{lo}-{hi}%{'':<10} {len(sub):>5} {rate*100:>9.1f}% {rate/base:>6.2f}x")

# D 日开盘封单 → D+1 涨停
print("\n--- D 日开盘封单占比 → D+1 涨停率 ---")
print(f"{'区间':<15} {'n':>5} {'D+1涨停率':>10} {'lift':>6}")
print("-"*45)
for lo, hi in [(0,0.1),(0.1,1),(1,3),(3,5),(5,10),(10,9999)]:
    sub = J[(J["open_seal_pct"]>=lo)&(J["open_seal_pct"]<hi)]
    if len(sub)==0: continue
    rate = sub["next_zt"].mean()
    print(f"{lo}-{hi}%{'':<10} {len(sub):>5} {rate*100:>9.1f}% {rate/base:>6.2f}x")

# 双高 → D+1
print("\n--- 双高 (D 日) → D+1 涨停率 ---")
for x, y in [(5,1),(10,1),(10,3),(20,3),(20,5),(50,5)]:
    sub = J[(J["yedan_pct"]>=x)&(J["open_seal_pct"]>=y)]
    if len(sub)==0:
        print(f"  ≥{x}% + ≥{y}%: n=0")
        continue
    rate = sub["next_zt"].mean()
    print(f"  ≥{x}% + ≥{y}%: n={len(sub):>3}, D+1涨停率 {rate*100:.1f}% (lift {rate/base:.2f}x)")

# ===== 涨停股封流比 → 次日反包 =====
print("\n" + "="*70)
print("【封流比反包验证】 D 涨停股 + 封流比 → D+1 是否再涨停")
print("="*70)

j2 = []
for i, d in enumerate(dates[:-1]):
    d_next = dates[i+1]
    fl = all_fl[d].copy()
    fl_next_codes = set(all_fl[d_next]["股票代码"].astype(str).tolist())
    fl["next_zt"] = fl["股票代码"].astype(str).isin(fl_next_codes)
    j2.append(fl)
J2 = pd.concat(j2, ignore_index=True)
J2 = J2[~J2["股票简称"].astype(str).str.contains("ST", na=False)]
print(f"样本: {len(J2)} 行 (D 涨停股, D+1 是否再封)")
print(f"基线连板率: {J2['next_zt'].mean()*100:.1f}%")

print(f"\n{'封流比':<12} {'n':>5} {'D+1再涨停':>10} {'lift':>6}")
print("-"*45)
base2 = J2["next_zt"].mean()
for lo, hi in [(0,0.5),(0.5,1),(1,3),(3,5),(5,10),(10,9999)]:
    sub = J2[(J2["fenglu_ratio"]>=lo)&(J2["fenglu_ratio"]<hi)]
    if len(sub)==0: continue
    rate = sub["next_zt"].mean()
    print(f"{lo}-{hi}{'':<8} {len(sub):>5} {rate*100:>9.1f}% {rate/base2:>6.2f}x")

# 炸板次数 → 次日表现
print(f"\n--- 炸板次数 → D+1 再涨停率 ---")
J2["kaiban"] = pd.to_numeric(J2["kaiban"] if "kaiban" in J2.columns else J2["涨停开板次数[20260430]"] if "涨停开板次数[20260430]" in J2.columns else 0, errors="coerce")
# 重新拉炸板字段 (列名因日期不同)
def get_kaiban(row):
    for c in row.index:
        if "涨停开板次数" in str(c):
            v = row[c]
            try: return int(v)
            except: return 0
    return 0
J2["kaiban_n"] = J2.apply(get_kaiban, axis=1)
print(f"{'炸板次数':<12} {'n':>5} {'D+1涨停率':>10} {'lift':>6}")
print("-"*45)
for k in [0,1,2,3]:
    sub = J2[J2["kaiban_n"]==k]
    if len(sub)==0: continue
    rate = sub["next_zt"].mean()
    print(f"{k} 次{'':<10} {len(sub):>5} {rate*100:>9.1f}% {rate/base2:>6.2f}x")
sub = J2[J2["kaiban_n"]>=4]
if len(sub)>0:
    rate = sub["next_zt"].mean()
    print(f"≥4 次{'':<8} {len(sub):>5} {rate*100:>9.1f}% {rate/base2:>6.2f}x")
