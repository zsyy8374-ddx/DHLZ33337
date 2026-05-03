"""
picks_v9_5_6.py — 用 v9 战法 (主升板块过滤) 生成 5-6 候选股

逻辑:
1. 加载 4-30 涨停股 (问财) + 4-30 候选股 (daily_picks v2.5)
2. 加载 8 日板块趋势 → 真主升板块 (8 天 ≥5 天进 Top 20)
3. 重打分: v2.5 总分 + 主升板块加分 + 趋势加分
4. 输出 Top 10 给董哥
"""
import json
import csv
import pandas as pd
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path('/Users/openclaw/.openclaw/workspace-dengxian')
OUT = WORKSPACE / 'mx_output'

# ── 1. 加载 8 日板块趋势 ──
trend = pd.read_csv(OUT / 'sector_trend_8day_2026-04-21_to_30.csv')
print(f"✅ 加载板块趋势: {len(trend)} 个板块")

# 真主升板块 (≥5 天进 Top 20)
mainline = set(trend[trend['Top20天数'] >= 5]['板块'].tolist())
# 强势板块 (≥3 天进 Top 20)
strong = set(trend[trend['Top20天数'] >= 3]['板块'].tolist())
# 趋势变好的板块 (4-30 排名 ≤ 10)
TREND_TOP_4_30 = set(trend[trend['2026-04-30'].astype(str).apply(lambda x: x.replace('.0','').isdigit() and int(float(x)) <= 10)]['板块'].tolist())

print(f"  真主升 (≥5天Top20): {len(mainline)} 个 → {sorted(mainline)}")
print(f"  强势  (≥3天Top20): {len(strong)} 个")
print(f"  4-30 当日 Top 10: {len(TREND_TOP_4_30)} 个 → {sorted(TREND_TOP_4_30)}")

# ── 2. 加载 4-30 涨停股 (问财) ──
zt = pd.read_csv(OUT / 'wencai_zt_2026-04-30.csv')
zt['code'] = zt['股票代码'].astype(str).str.split('.').str[0]
print(f"\n✅ 加载 4-30 涨停股 (问财): {len(zt)} 只")

# 找列
def find_col(df, key, ymd='20260430'):
    for c in df.columns:
        if key in c and ymd in c: return c
    for c in df.columns:
        if key in c: return c
    return None

col_lbc = find_col(zt, '几天几板')
col_main = find_col(zt, '主力净流入') or find_col(zt, '主力')
col_concept = '所属概念'
col_amt = find_col(zt, '成交额')
col_volr = find_col(zt, '量比')
col_ltsz = find_col(zt, 'a股市值') or find_col(zt, '流通市值')
col_chg5 = find_col(zt, '区间涨跌幅')

import re
def parse_lbc(v):
    if pd.isna(v): return 1
    s = str(v).strip()
    if s == '首板涨停': return 1
    m = re.search(r'(\d+)\s*天\s*(\d+)\s*板', s)
    if m: return int(m.group(2))
    return 1

zt['lbc'] = zt[col_lbc].apply(parse_lbc) if col_lbc else 1

# ── 3. 重打分 ──
candidates = []
for _, r in zt.iterrows():
    code = r['code']
    name = r['股票简称']
    lbc = r['lbc']
    concepts_str = str(r[col_concept]) if pd.notna(r[col_concept]) else ''
    concepts = [c.strip() for c in concepts_str.split(';') if c.strip()]
    
    # 主升板块匹配
    matched_mainline = [c for c in concepts if c in mainline]
    matched_strong   = [c for c in concepts if c in strong]
    matched_today    = [c for c in concepts if c in TREND_TOP_4_30]
    
    # 评分
    score = 0
    score += lbc * 8                         # 连板高度
    score += min(len(matched_mainline), 3) * 12   # 主升板块 (上限 3 个)
    score += min(len(matched_strong), 5) * 4      # 强势板块 (上限 5)
    score += len(matched_today) * 3                # 4-30 当日热点
    
    # 排除股
    if name and ('ST' in name or '*' in name): 
        score -= 30  # ST 减分

    # 主力净流入加分
    main_str = str(r[col_main]) if col_main and pd.notna(r[col_main]) else ''
    main = 0
    if '亿' in main_str: 
        try: main = float(main_str.replace('亿','')) 
        except: main = 0
    elif '万' in main_str: 
        try: main = float(main_str.replace('万','')) / 1e4
        except: main = 0
    else:
        try: main = float(main_str) / 1e8
        except: main = 0
    score += min(main * 2, 20)  # 主力流入(亿)*2, 上限 20
    
    candidates.append({
        'code': code,
        'name': name,
        'lbc': lbc,
        'score': round(score, 1),
        'main_yi': round(main, 2),
        'mainline': '/'.join(matched_mainline) if matched_mainline else '-',
        'strong': '/'.join(matched_strong[:5]),
        'today_top': '/'.join(matched_today),
        'all_concepts': concepts_str[:80],
    })

df = pd.DataFrame(candidates).sort_values('score', ascending=False).reset_index(drop=True)

# ── 4. 输出 Top 12 ──
print(f"\n=== 5-6 候选股 v9 (基于 4-30 涨停 + 8 日板块趋势) ===\n")
print(f"{'排':>2s} {'代码':>7s} {'名称':<10s} {'连板':>3s} {'主力(亿)':>7s} {'分':>5s}  {'主升板块':<25s} {'4-30当日':<20s}")
print('-' * 130)
for i, r in df.head(15).iterrows():
    print(f"{i+1:>2d} {r['code']:>7s} {r['name'][:10]:<10s} "
          f"{int(r['lbc']):>3d}板 "
          f"{r['main_yi']:>7.2f} "
          f"{r['score']:>5.1f}  "
          f"{r['mainline'][:25]:<25s} "
          f"{r['today_top'][:20]:<20s}")

# 写文件
out_csv = WORKSPACE / 'picks' / 'picks_v9_5-6.csv'
df.to_csv(out_csv, index=False, encoding='utf-8-sig')
print(f"\n✅ 写入 {out_csv}")

# 也输出一个简洁的 markdown
md = ['# 5-6 周二候选股 v9\n']
md.append(f"基于 4-30 涨停 + 8 日板块趋势 (4-21~4-30)\n")
md.append(f"\n## 真主升板块筛选 (本期)\n")
md.append(f"- 8 天里 ≥5 天进 Top 20 的板块: **{', '.join(sorted(mainline))}**\n")
md.append(f"\n## Top 10 候选\n")
md.append(f"| 排 | 代码 | 名称 | 连板 | 主力(亿) | 综合分 | 所属主升 | 4-30 热点 |\n")
md.append(f"|---:|:---:|:---|---:|---:|---:|:---|:---|\n")
for i, r in df.head(10).iterrows():
    md.append(f"| {i+1} | {r['code']} | {r['name']} | {r['lbc']}板 | {r['main_yi']:.2f} | {r['score']:.1f} | {r['mainline']} | {r['today_top']} |\n")

out_md = WORKSPACE / 'picks' / 'picks_v9_5-6.md'
out_md.write_text(''.join(md), encoding='utf-8')
print(f"✅ 写入 {out_md}")
