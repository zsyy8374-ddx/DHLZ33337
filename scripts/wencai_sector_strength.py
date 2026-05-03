#!/usr/bin/env python3
"""
板块强度 v0.2: 用首封时间 + 炸板率 + 封流比综合识别真主升板块
对比之前 v2.7 失败 (只用涨停集中度), 这次加细致的"硬度"维度

策略:
- 真主升板块 = 早封多 + 不炸板多 + 封流比硬
- 题材股板块 = 晚封多 + 炸板率高 + 封流比软
"""
import warnings
warnings.filterwarnings('ignore')

from pathlib import Path
import pandas as pd
import re
from collections import defaultdict

DATA = Path("/Users/openclaw/.openclaw/workspace-dengxian/data/wencai")

# 加载所有 fenglu
all_fl = []
for f in sorted(DATA.glob("fenglu_*.csv")):
    df = pd.read_csv(f, dtype={"code":str,"股票代码":str})
    df["date"] = f.stem.replace("fenglu_","")
    all_fl.append(df)
fl = pd.concat(all_fl, ignore_index=True)
fl = fl[~fl["股票简称"].astype(str).str.contains("ST", na=False)]

# 时间转分钟
def t2min(s):
    if pd.isna(s): return None
    parts = str(s).strip().split(":")
    if len(parts)<2: return None
    try: return int(parts[0])*60+int(parts[1])
    except: return None

fl["fenglu_ratio"] = pd.to_numeric(fl["fenglu_ratio"], errors="coerce")
fl["first_min"] = fl["zt_first_time"].apply(t2min)
fl["last_min"] = fl["zt_last_time"].apply(t2min)

# 炸板字段 (各日列名不同, 通用提取)
def get_kaiban(row):
    for c in row.index:
        if "涨停开板次数" in str(c):
            try: return int(row[c])
            except: return 0
    return 0
fl["kaiban"] = fl.apply(get_kaiban, axis=1)

# 概念字段
def get_concepts(row):
    for c in row.index:
        if "涨停原因类别" in str(c):
            return str(row[c]) if pd.notna(row[c]) else ""
    return ""
fl["concepts"] = fl.apply(get_concepts, axis=1)

print(f"样本: {len(fl)} 涨停股 (4 月 19 天非 ST)")

# 拆概念聚合
sect_daily = defaultdict(lambda: defaultdict(list))  # date -> concept -> [rows]
for _, row in fl.iterrows():
    for c in re.split(r'[+]', row["concepts"]):
        c = c.strip()
        if c:
            sect_daily[row["date"]][c].append(row)

# 全月聚合 (≥10 只 = 主流概念, 高频出现)
all_concepts = defaultdict(list)
for d, sd in sect_daily.items():
    for c, rows in sd.items():
        if len(rows) >= 2:  # 单日 ≥2 只才算"上榜"
            all_concepts[c].append({
                "date": d,
                "n": len(rows),
                "first_min_avg": sum(r["first_min"] for r in rows if r["first_min"])/max(1,sum(1 for r in rows if r["first_min"])),
                "kaiban_avg": sum(r["kaiban"] for r in rows)/len(rows),
                "kaiban_0_pct": sum(1 for r in rows if r["kaiban"]==0)/len(rows),
                "fenglu_avg": sum(r["fenglu_ratio"] for r in rows if pd.notna(r["fenglu_ratio"]))/max(1,sum(1 for r in rows if pd.notna(r["fenglu_ratio"]))),
            })

print(f"\n全月主流概念 (上榜 ≥5 天)")
print(f"{'板块':<20} {'天数':>4} {'平均n':>5} {'首封均':>7} {'0炸%':>6} {'封流均':>6} {'强度':>6}")
print("-"*70)

def m2t(m):
    if pd.isna(m): return ''
    h, mi = divmod(int(m), 60)
    return f"{h:02d}:{mi:02d}"

ranked = []
for c, days_data in all_concepts.items():
    if len(days_data) < 5:  # 至少上榜 5 天
        continue
    n_avg = sum(d["n"] for d in days_data)/len(days_data)
    fm_avg = sum(d["first_min_avg"] for d in days_data)/len(days_data)
    k0_avg = sum(d["kaiban_0_pct"] for d in days_data)/len(days_data)
    fl_avg = sum(d["fenglu_avg"] for d in days_data)/len(days_data)
    
    # 综合强度评分
    # 首封早 (越小越好, 满分 600=10:00 前): (660-fm)/100 * 30
    # 0 炸板比例: k0 * 30
    # 封流比: min(fl,5)/5 * 25
    # 上榜频率: len(days)/19 * 15
    score_first = max(0, (660-fm_avg)/120) * 30
    score_kaiban = k0_avg * 30
    score_fenglu = min(fl_avg, 5)/5 * 25
    score_freq = len(days_data)/19 * 15
    total = score_first + score_kaiban + score_fenglu + score_freq
    
    ranked.append({
        "板块": c, "上榜天数": len(days_data), "平均n": n_avg,
        "首封均": fm_avg, "0炸板%": k0_avg*100,
        "封流均": fl_avg, "强度": total
    })

ranked.sort(key=lambda x: -x["强度"])
for r in ranked[:25]:
    print(f"{r['板块'][:18]:<20} {r['上榜天数']:>4} {r['平均n']:>5.1f} "
          f"{m2t(r['首封均']):>7} {r['0炸板%']:>5.0f}% {r['封流均']:>6.2f} {r['强度']:>6.1f}")

print(f"\n{'='*70}")
print("板块强度 v0.2 校验: 看每个排名前 5 板块的最近 3 天表现")
print('='*70)

# 看排名前 5 板块在最后 3 天的成员是否真涨停 → 验证"主升板块"持续性
recent_dates = sorted(sect_daily.keys())[-3:]
for r in ranked[:5]:
    name = r["板块"]
    print(f"\n📊 {name} (强度 {r['强度']:.1f})")
    for d in recent_dates:
        rows = sect_daily[d].get(name, [])
        if not rows: continue
        names = [str(x.get("股票简称","")) for x in rows]
        print(f"  {d}: n={len(rows)}, 票: {', '.join(names[:6])}{'...' if len(names)>6 else ''}")
