"""
sector_strength_v8.py — 妙想 + akshare + 问财 三源融合板块强度

数据源:
  1. akshare ths 概念资金流 → 板块涨幅、净流入、公司家数、领涨股 (387 个板块)
  2. 问财 wencai → 涨停股的真"几天几板" (准的连板, 妙想这字段是错的)
  3. 妙想/wencai 涨停股 → 反推每个板块的涨停家数 + 主力流入合计

输出 csv: 排名, 板块, 板块涨幅, 板块净流入(亿), 公司家数, 涨停家数, ≥2板, ≥3板, 龙头连板, 领涨股, 综合分
"""
import pandas as pd
import csv
from collections import defaultdict
from pathlib import Path

OUT = Path('/Users/openclaw/.openclaw/workspace-dengxian/mx_output')
DATE = '2026-04-30'

# === 1. 加载 akshare 板块资金流 ===
fund = pd.read_csv(OUT / 'ak_concept_fund_flow_realtime.csv')
fund.columns = [c.strip() for c in fund.columns]
print(f"akshare 板块资金流: {len(fund)} 个板块")

# === 2. 加载问财涨停股 + 几天几板 ===
wc = pd.read_csv(OUT / f'wencai_zt_{DATE}.csv')
wc['code'] = wc['股票代码'].astype(str).str.split('.').str[0]
print(f"问财 4-30 涨停: {len(wc)} 只")

def parse_lbc(v):
    """从 '几天几板' 字段提取连板数"""
    if pd.isna(v): return 1
    s = str(v).strip()
    if s == '首板涨停': return 1
    # '10天8板', '2天2板', '3天2板'
    if '板' in s:
        parts = s.split('板')[0].split('天')
        if len(parts) == 2:
            return int(parts[1])
    return 1

wc['lbc'] = wc['几天几板[20260430]'].apply(parse_lbc)
print("\n=== 问财识别的连板梯队 ===")
multi = wc[wc['lbc'] >= 2].sort_values('lbc', ascending=False)
for _, r in multi.iterrows():
    print(f"  {r['code']} {r['股票简称']}  {r['几天几板[20260430]']}  连板{r['lbc']}")

# === 3. 加载妙想涨停股 (Top 27 主力降序) — 拿主力净流入 ===
mx = pd.read_csv(OUT / 'mx_xuangu_所有概念板块_按4-30主力净流入降序_板块名称_涨幅_涨停家数_成交额_量比_主力净流入资金_5日涨幅.csv')
print(f"\n妙想 Top 27: {len(mx)} 只 (按主力净流入降序)")

def parse_amt(s):
    if pd.isna(s): return 0
    s = str(s).strip().replace('元','').replace(',','')
    if '亿' in s: return float(s.replace('亿',''))*1e8
    if '万' in s: return float(s.replace('万',''))*1e4
    try: return float(s)
    except: return 0

mx['main_yi'] = mx['主力净额(元) 2026.04.30'].apply(parse_amt) / 1e8
mx_main_map = dict(zip(mx['代码'].astype(str), mx['main_yi']))

# === 4. 反推每个板块: 涨停家数 + ≥2板 + ≥3板 + 龙头连板 + 主力流入合计 ===
EXCLUDE = {'融资融券','沪股通','深股通','国企改革','新股与次新股','上证A50','上证180','上证380','上证50',
           '沪深300','HS300','中证500','中证1000','中证800','深成500','ST板块','MSCI中国','专精特新',
           '上证AB股','上证A股','上证上市公司','上证主板A股','全部AB股','全部A股','全部A股(非ST)','全部A股(非金融)','全部上市公司',
           '沪深AB股','沪深A股','沪深主板A股','沪深股通','沪股通(可融资融券)','创业板','创业板综','创业板50','创业成份',
           '深股通(可融资融券)','深证AB股','深证A股','深证上市公司','深证主板A股','深证100R','科创50','科创创业50','科创板',
           '小盘股','中盘股','大盘股','中盘成长','小盘成长','中盘价值','小盘价值','大盘成长',
           '股权转让(并购重组)','一带一路','西部大开发','京津冀','长江三角','长江三角洲','京津冀一体化',
           '富时罗素','标准普尔','东方财富热股','破发股','低价股','微利股','破增发价股',
           '昨日首板','昨日高振幅','昨日高换手','最近多板','近期新高','百日新高','历史新高',
           '权重股','央国企改革','央国企','国企改革','*ST','风险警示板',}

sec_zt   = defaultdict(int)
sec_zt2  = defaultdict(int)
sec_zt3  = defaultdict(int)
sec_max_lbc = defaultdict(int)
sec_main = defaultdict(float)
sec_members = defaultdict(list)

for _, r in wc.iterrows():
    code = r['code']
    name = r['股票简称']
    lbc = r['lbc']
    main = mx_main_map.get(code, 0)
    concepts_str = r['所属概念'] if pd.notna(r['所属概念']) else ''
    concepts = [c.strip() for c in concepts_str.split(';') if c.strip() and c.strip() not in EXCLUDE]
    for c in concepts:
        sec_zt[c] += 1
        if lbc >= 2: sec_zt2[c] += 1
        if lbc >= 3: sec_zt3[c] += 1
        sec_max_lbc[c] = max(sec_max_lbc[c], lbc)
        sec_main[c] += main
        sec_members[c].append(f"{code}{name}({lbc}板)")

# === 5. 跟 akshare 板块表 join ===
fund['板块'] = fund['行业']
fund['板块涨幅'] = fund['行业-涨跌幅']
fund['板块净额(亿)'] = fund['净额']  # 已经是亿
fund['公司家数'] = fund['公司家数']

# 加 zt 数据
fund['涨停家数'] = fund['板块'].map(lambda x: sec_zt.get(x, 0))
fund['≥2板'] = fund['板块'].map(lambda x: sec_zt2.get(x, 0))
fund['≥3板'] = fund['板块'].map(lambda x: sec_zt3.get(x, 0))
fund['龙头连板'] = fund['板块'].map(lambda x: sec_max_lbc.get(x, 0))
fund['涨停股主力(亿)'] = fund['板块'].map(lambda x: sec_main.get(x, 0))

# 综合分: 板块净额 (主) + 涨停密度奖励 + 龙头连板奖励
fund['综合分'] = (
    fund['板块净额(亿)']                                          # 板块整体资金
    + fund['涨停家数'] * 5                                          # 涨停密度
    + fund['≥2板'] * 10                                              # 连板密度
    + fund['≥3板'] * 20                                              # 高位连板
    + fund['龙头连板'].clip(upper=10) * 8                           # 龙头高度
    + fund['板块涨幅'] * 3                                           # 板块涨幅
)

# 排除宽泛
fund = fund[~fund['板块'].isin(EXCLUDE)].copy()

# 按综合分降序
fund = fund.sort_values('综合分', ascending=False).reset_index(drop=True)

print(f"\n=== v8 综合板块强度 Top 30 ({DATE}) ===\n")
print(f"{'排':>2s} {'板块':<14s} {'涨幅':>5s} {'板净额':>7s} {'家数':>4s} {'涨停':>4s} {'≥2板':>4s} {'≥3板':>4s} {'龙':>3s} {'综合':>6s} {'领涨':<8s}")
print('-' * 100)

for i, r in fund.head(30).iterrows():
    print(f"{i+1:>2d} {str(r['板块'])[:14]:<14s} "
          f"{r['板块涨幅']:>5.2f}% "
          f"{r['板块净额(亿)']:>7.1f} "
          f"{int(r['公司家数']):>4d} "
          f"{int(r['涨停家数']):>4d} "
          f"{int(r['≥2板']):>4d} "
          f"{int(r['≥3板']):>4d} "
          f"{int(r['龙头连板']):>3d} "
          f"{r['综合分']:>6.1f} "
          f"{str(r['领涨股'])[:8]:<8s}")

# 写 CSV
out_csv = OUT / f'sector_strength_v8_{DATE}.csv'
fund_out = fund[['板块','板块涨幅','板块净额(亿)','公司家数','涨停家数','≥2板','≥3板','龙头连板','涨停股主力(亿)','综合分','领涨股','领涨股-涨跌幅']]
fund_out.to_csv(out_csv, index=False, encoding='utf-8-sig')
print(f"\n✅ 写入 {out_csv}")
print(f"  共 {len(fund_out)} 个板块")
