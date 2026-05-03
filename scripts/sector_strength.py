"""
sector_strength.py — 三源融合板块强度 (任意日期)

用法:
  python3 sector_strength.py 2026-04-30
  python3 sector_strength.py 2026-04-29
  python3 sector_strength.py            # 默认昨天最近交易日

数据源 (按交易日历史):
  1. 问财 wencai → 该日涨停股 (代码、几天几板、所属概念、主力净流入、5日涨幅)
  2. akshare 板块历史涨跌 → 板块整体涨跌 (注: 资金流接口只有当天, 历史靠成分股聚合)
  3. 反推: 板块涨停家数 / ≥2 板 / ≥3 板 / 龙头连板 / 主力流入合计

输出:
  mx_output/sector_strength_<DATE>.csv
"""
import sys
import re
import pandas as pd
import pywencai
from collections import defaultdict
from pathlib import Path

OUT = Path('/Users/openclaw/.openclaw/workspace-dengxian/mx_output')
OUT.mkdir(exist_ok=True)

# ── 排除宽泛标签 ──
EXCLUDE = {
    '融资融券','沪股通','深股通','国企改革','新股与次新股',
    '上证180','上证50','上证AB股','上证A股','上证上市公司','上证主板A股',
    '全部AB股','全部A股','全部A股(非ST)','全部A股(非金融)','全部上市公司',
    '沪深300','HS300','中证500','中证1000','中证800','深成500','沪深AB股','沪深A股','沪深主板A股','沪深股通','沪股通(可融资融券)',
    '深股通(可融资融券)','深证AB股','深证A股','深证上市公司','深证主板A股','深证100R',
    '创业板','创业板综','创业板50','创业成份','科创50','科创创业50','科创板',
    'ST板块','MSCI中国','专精特新','*ST','风险警示板',
    '小盘股','中盘股','大盘股','中盘成长','小盘成长','中盘价值','小盘价值','大盘成长',
    '股权转让(并购重组)','一带一路','西部大开发','京津冀','长江三角','长江三角洲','京津冀一体化',
    '富时罗素','标准普尔','东方财富热股','破发股','低价股','微利股','破增发价股',
    '昨日首板','昨日高振幅','昨日高换手','最近多板','近期新高','百日新高','历史新高',
    '权重股','央国企改革','央国企',
}


def parse_lbc(v):
    """从 '几天几板' 提取连板数; '首板涨停' = 1, '10天8板' = 8"""
    if pd.isna(v): return 1
    s = str(v).strip()
    if s in ('首板涨停', '-', ''): return 1
    m = re.search(r'(\d+)\s*天\s*(\d+)\s*板', s)
    if m:
        return int(m.group(2))
    return 1


def parse_amt(s):
    """金额: '6.24亿' / '5259.08万' / 数值字符串"""
    if pd.isna(s): return 0
    s = str(s).strip().replace('元', '').replace(',', '')
    if '亿' in s: return float(s.replace('亿', '')) * 1e8
    if '万' in s: return float(s.replace('万', '')) * 1e4
    try: return float(s)
    except: return 0


def fetch_zt(date_str):
    """问财拉指定日期涨停股. date_str: 2026-04-30
    
    教训: 字段太多 wencai 会截断/失败, 用简单 query 拿 100 行,
    再用第二次 query 补字段 (concept/连板).
    """
    md = date_str.replace('-', '')[4:]  # 0430
    md_h = f"{int(md[:2])}月{int(md[2:])}日"  # 4月30日
    
    # Pass 1: 简单 query 拿全涨停股 + 基本字段
    q1 = f"{md_h}涨停"
    print(f"问财 P1: {q1}")
    df = pywencai.get(query=q1, perpage=200, loop=True)
    if df is None or len(df) == 0:
        raise RuntimeError(f"问财 {date_str} 无数据")
    df['code'] = df['股票代码'].astype(str).str.split('.').str[0]
    print(f"  → P1 拿到 {len(df)} 行 × {len(df.columns)} 列")
    
    # Pass 2: 拉概念 + 连板 + 主力
    q2 = f"{md_h}涨停的股票, 几天几板、所属概念、主力净流入、5日涨幅、量比"
    print(f"问财 P2: {q2}")
    df2 = pywencai.get(query=q2, perpage=200, loop=True)
    if df2 is not None and len(df2) > 0:
        df2['code'] = df2['股票代码'].astype(str).str.split('.').str[0]
        print(f"  → P2 拿到 {len(df2)} 行 × {len(df2.columns)} 列")
        # 把 P2 的列合到 P1
        for col in df2.columns:
            if col not in df.columns and col != 'code':
                df = df.merge(df2[['code', col]], on='code', how='left')
    return df


def fetch_concept_fund_flow(date_str):
    """
    问财拉某日所有同花顺概念板块的板块涨幅 + 主力净流入.
    问财对"概念板块"返回的是成分股, 但我们拉:
       'YYYY-MM-DD 同花顺概念板块涨跌幅排名'
    它会返回板块指数级别数据.
    """
    md = date_str.replace('-', '')[4:]
    md_h = f"{int(md[:2])}月{int(md[2:])}日"
    q = f"{md_h}同花顺概念板块涨跌幅、主力净流入、成交额、5日涨幅, 按主力净流入降序"
    print(f"问财(板块): {q}")
    try:
        df = pywencai.get(query=q, perpage=500, loop=True, query_type='zhishu')
    except Exception:
        df = pywencai.get(query=q, perpage=500, loop=True)
    return df


def main(date_str):
    print(f"\n{'='*60}\n  板块强度 v8 — {date_str}\n{'='*60}")

    # ── 1. 涨停股 ──
    wc = fetch_zt(date_str)
    print(f"✅ 涨停股 {len(wc)} 只\n")

    # 找列名 (列名带 [YYYYMMDD])
    ymd = date_str.replace('-', '')
    col_lbc  = next((c for c in wc.columns if '几天几板' in c and ymd in c), None) or next((c for c in wc.columns if '几天几板' in c), None)
    col_main = next((c for c in wc.columns if '主力' in c and ymd in c), None) or next((c for c in wc.columns if '主力' in c), None)
    col_chg5 = next((c for c in wc.columns if '区间涨跌幅' in c), None)
    col_amt  = next((c for c in wc.columns if '成交额' in c and ymd in c), None) or next((c for c in wc.columns if '成交额' in c), None)
    col_volr = next((c for c in wc.columns if '量比' in c), None)
    col_concept = next((c for c in wc.columns if '所属概念' in c and '数量' not in c), None)

    print(f"列映射: 几天几板={col_lbc}, 主力={col_main}, 5日={col_chg5}, 概念={col_concept}")

    wc['lbc']  = wc[col_lbc].apply(parse_lbc) if col_lbc else 1
    wc['main'] = wc[col_main].apply(parse_amt) if col_main else 0
    wc['chg5'] = pd.to_numeric(wc[col_chg5], errors='coerce').fillna(0) if col_chg5 else 0
    wc['amt']  = wc[col_amt].apply(parse_amt) if col_amt else 0
    wc['volr'] = pd.to_numeric(wc[col_volr], errors='coerce').fillna(0) if col_volr else 0
    wc['concepts'] = wc[col_concept].fillna('') if col_concept else ''

    print(f"\n=== {date_str} 连板梯队 ===")
    multi = wc[wc['lbc'] >= 2].sort_values('lbc', ascending=False)
    if len(multi) == 0:
        print("(全是首板, 无连板)")
    else:
        for _, r in multi.iterrows():
            print(f"  {r['code']} {r['股票简称']:<10s}  {r[col_lbc]}  连板{r['lbc']}")

    # ── 2. 反推板块 ──
    sec_zt   = defaultdict(int)
    sec_zt2  = defaultdict(int)
    sec_zt3  = defaultdict(int)
    sec_max_lbc = defaultdict(int)
    sec_main = defaultdict(float)
    sec_amt  = defaultdict(float)
    sec_5d   = defaultdict(list)
    sec_volr = defaultdict(list)
    sec_members = defaultdict(list)

    for _, r in wc.iterrows():
        concepts = [c.strip() for c in str(r['concepts']).split(';') if c.strip() and c.strip() not in EXCLUDE]
        for c in concepts:
            sec_zt[c] += 1
            if r['lbc'] >= 2: sec_zt2[c] += 1
            if r['lbc'] >= 3: sec_zt3[c] += 1
            sec_max_lbc[c] = max(sec_max_lbc[c], r['lbc'])
            sec_main[c] += r['main']
            sec_amt[c]  += r['amt']
            sec_5d[c].append(r['chg5'])
            sec_volr[c].append(r['volr'])
            sec_members[c].append(f"{r['code']}{r['股票简称']}({r['lbc']}板)")

    # ── 3. 综合分 ──
    rows = []
    for s in sec_zt.keys():
        zt   = sec_zt[s]
        zt2  = sec_zt2[s]
        zt3  = sec_zt3[s]
        lbc  = sec_max_lbc[s]
        main = sec_main[s] / 1e8
        amt  = sec_amt[s] / 1e8
        chg5 = sum(sec_5d[s])/len(sec_5d[s]) if sec_5d[s] else 0
        volr = sum(sec_volr[s])/len(sec_volr[s]) if sec_volr[s] else 0
        # 综合分: 涨停密度 + 连板 + 高位 + 主力 + 5日强度
        score = (
            zt * 5
            + zt2 * 10
            + zt3 * 20
            + min(lbc, 10) * 8
            + main * 2          # 主力流入(亿) 加权
            + chg5 * 0.5        # 5日涨幅
        )
        rows.append({
            '板块': s,
            '涨停家数': zt,
            '≥2板': zt2,
            '≥3板': zt3,
            '龙头连板': lbc,
            '主力(亿)': round(main, 2),
            '成交额(亿)': round(amt, 2),
            '5日均(%)': round(chg5, 2),
            '量比均': round(volr, 2),
            '综合分': round(score, 1),
            '成员(Top5)': '; '.join(sec_members[s][:5]),
        })

    df = pd.DataFrame(rows).sort_values('综合分', ascending=False).reset_index(drop=True)
    df.index += 1

    print(f"\n=== Top 25 板块 ===\n")
    print(f"{'排':>2s} {'板块':<14s} {'涨停':>4s} {'≥2板':>4s} {'≥3板':>4s} {'龙':>3s} {'主力(亿)':>8s} {'5日':>6s} {'综合':>6s}")
    print('-' * 90)
    for i, r in df.head(25).iterrows():
        print(f"{i:>2d} {str(r['板块'])[:14]:<14s} "
              f"{int(r['涨停家数']):>4d} "
              f"{int(r['≥2板']):>4d} "
              f"{int(r['≥3板']):>4d} "
              f"{int(r['龙头连板']):>3d} "
              f"{r['主力(亿)']:>8.2f} "
              f"{r['5日均(%)']:>6.2f} "
              f"{r['综合分']:>6.1f}")

    out_csv = OUT / f'sector_strength_{date_str}.csv'
    df.to_csv(out_csv, index=False, encoding='utf-8-sig')
    print(f"\n✅ 写入 {out_csv}")
    print(f"  共 {len(df)} 个板块, 排除宽泛标签后")

    # 也把 raw 涨停股留底
    raw_csv = OUT / f'wencai_zt_{date_str}.csv'
    wc.to_csv(raw_csv, index=False, encoding='utf-8-sig')
    print(f"✅ 涨停股留底 {raw_csv}")

    return df


if __name__ == '__main__':
    if len(sys.argv) > 1:
        date_str = sys.argv[1]
    else:
        from datetime import datetime, timedelta
        # 默认: 最近一个工作日 (周一返回上周五)
        d = datetime.now()
        while d.weekday() >= 5:  # 周六周日
            d -= timedelta(days=1)
        if d.date() == datetime.now().date():  # 今天还没收盘的话
            d -= timedelta(days=1)
            while d.weekday() >= 5:
                d -= timedelta(days=1)
        date_str = d.strftime('%Y-%m-%d')
    main(date_str)
