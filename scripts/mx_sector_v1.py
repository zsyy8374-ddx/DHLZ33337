"""
mx_sector_v1.py — 用妙想涨停股反推板块强度表

董哥要的字段:
  板块名称、成员数*、涨跌幅*、涨停家数、≥2板家数、≥3板家数、龙头连板高度、
  成交额*、量比*、主力净流入资金、5日累计涨幅*

* 板块级字段(成员数/涨跌幅/成交额/量比/5日涨幅): 由涨停成员推算 (中位数/合计)
  真正完整数据要每个板块单独查指数, 这里只用涨停股反推

输出: 板块名称, 涨停家数, ≥2板, ≥3板, 龙头板高, 主力流入合计, 主力流入均值, 5日涨幅均值
按主力流入降序
"""
import csv, sys
from collections import defaultdict
from pathlib import Path

CSV = Path('/Users/openclaw/.openclaw/workspace-dengxian/mx_output/mx_xuangu_4-30涨停的股票,_字段__代码、名称、涨跌幅、涨停、首板、所属概念、连续涨停天数、几天几板、成交额、量比、主力净流入、5日涨幅、流通市值.csv')

# 排除宽泛标签
EXCLUDE = {'融资融券','沪股通','深股通','国企改革','新股与次新股','上证A50','上证180_','上证380','上证50_',
           '沪深300','HS300_','中证500','中证1000','深成500','ST板块','MSCI中国','专精特新','小盘股',
           '中盘股','大盘股','中盘成长','小盘成长','中盘价值','小盘价值','大盘成长',
           '股权转让(并购重组)','一带一路','西部大开发','京津冀','长江三角','长江三角洲',
           '富时罗素','标准普尔','东方财富热股','破发股','低价股','微利股','破增发价股',
           '昨日首板','昨日高振幅','昨日高换手','最近多板','近期新高','百日新高 ','历史新高 ',
           '权重股','央国企改革','央国企','国企改革','创业板综','创业成份',}

def parse_amt(s):
    if not s: return 0
    s = s.strip().replace('元','').replace(',','')
    if '亿' in s: return float(s.replace('亿',''))*1e8
    if '万' in s: return float(s.replace('万',''))*1e4
    try: return float(s)
    except: return 0

def parse_int(s):
    if not s: return 0
    try: return int(float(s))
    except: return 0

def parse_pct(s):
    if not s: return 0
    s = s.replace('%','').strip()
    try: return float(s)
    except: return 0

with CSV.open(encoding='utf-8') as f:
    rows = list(csv.DictReader(f))

print(f"总涨停股: {len(rows)}\n")

# 先看看全部涨停股
print("=== 4-30 涨停股 (全部 71 只) ===")
print(f"{'代码':>8s} {'名称':<8s} {'涨幅':>6s} {'连板':>4s} {'主力':>10s} {'5日':>6s}")
for r in rows[:15]:
    name = r['股票简称'] or r['名称']
    print(f"  {r['代码']} {name[:6]:<6s}  {r['涨跌幅(%) 2026.04.30']:>6s}  "
          f"{r['连续涨停天数(天) 2026.04.30']:>3s}板 "
          f"{r['主力净额(元) 2026.04.30']:>10s} "
          f"{r['区间涨跌幅(%) 2026.04.24 - 2026.04.30']:>6s}")

# 反推板块
sec_zt = defaultdict(int)         # 涨停家数
sec_zt2 = defaultdict(int)        # ≥2 板
sec_zt3 = defaultdict(int)        # ≥3 板
sec_max_lbc = defaultdict(int)    # 龙头连板天数
sec_main = defaultdict(float)     # 主力净流入合计
sec_5d = defaultdict(list)        # 5 日涨幅列表
sec_amt = defaultdict(float)      # 成交额合计
sec_volr = defaultdict(list)      # 量比列表
sec_members = defaultdict(list)   # 成员列表

for r in rows:
    main = parse_amt(r['主力净额(元) 2026.04.30'])
    amt  = parse_amt(r['成交额(元) 2026.04.30'])
    lbc  = parse_int(r['连续涨停天数(天) 2026.04.30'])
    chg5 = parse_pct(r['区间涨跌幅(%) 2026.04.24 - 2026.04.30'])
    volr = parse_pct(r['量比 2026.04.30']) if r['量比 2026.04.30'] else 0
    name = r['股票简称'] or r['名称']
    code = r['代码']
    
    concepts = [c.strip() for c in r['概念'].split('、') if c.strip() and c.strip() not in EXCLUDE]
    for c in concepts:
        sec_zt[c] += 1
        if lbc >= 2: sec_zt2[c] += 1
        if lbc >= 3: sec_zt3[c] += 1
        sec_max_lbc[c] = max(sec_max_lbc[c], lbc)
        sec_main[c] += main
        sec_5d[c].append(chg5)
        sec_amt[c] += amt
        sec_volr[c].append(volr)
        sec_members[c].append(f"{code}{name}")

# 按主力净流入降序
sectors = sorted(sec_zt.keys(), key=lambda x: -sec_main[x])

print(f"\n=== 板块强度表 ({len(sectors)} 个板块, 按主力净流入降序, Top 30) ===\n")
print(f"{'排':>2s} {'板块':<14s} {'涨停':>4s} {'≥2板':>4s} {'≥3板':>4s} {'龙头':>4s} "
      f"{'主力(亿)':>9s} {'5日均(%)':>9s} {'量比均':>6s}")
print('-' * 90)

for i, s in enumerate(sectors[:30], 1):
    n = sec_zt[s]
    n2 = sec_zt2[s]
    n3 = sec_zt3[s]
    lbc = sec_max_lbc[s]
    main = sec_main[s] / 1e8
    chg5_avg = sum(sec_5d[s])/len(sec_5d[s]) if sec_5d[s] else 0
    volr_avg = sum(sec_volr[s])/len(sec_volr[s]) if sec_volr[s] else 0
    print(f"{i:>2d} {s[:14]:<14s} {n:>4d} {n2:>4d} {n3:>4d} {lbc:>3d}板 "
          f"{main:>9.2f} {chg5_avg:>9.2f} {volr_avg:>6.2f}")

# 写 CSV
out = Path('/Users/openclaw/.openclaw/workspace-dengxian/mx_output/sector_strength_v1_2026-04-30.csv')
with out.open('w', encoding='utf-8-sig', newline='') as f:
    w = csv.writer(f)
    w.writerow(['排名','板块','涨停家数','≥2板','≥3板','龙头连板','主力净流入(亿)','5日涨幅均值(%)','量比均值','成交额合计(亿)','成员数(涨停的)','成员名'])
    for i, s in enumerate(sectors, 1):
        w.writerow([i, s, sec_zt[s], sec_zt2[s], sec_zt3[s], sec_max_lbc[s],
                    f"{sec_main[s]/1e8:.2f}",
                    f"{sum(sec_5d[s])/len(sec_5d[s]):.2f}" if sec_5d[s] else "0",
                    f"{sum(sec_volr[s])/len(sec_volr[s]):.2f}" if sec_volr[s] else "0",
                    f"{sec_amt[s]/1e8:.2f}",
                    sec_zt[s],
                    "; ".join(sec_members[s][:5])])

print(f"\n✅ CSV 写入 {out}")
print(f"  共 {len(sectors)} 个板块, 按主力净流入降序")
