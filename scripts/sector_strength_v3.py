#!/usr/bin/env python3
"""板块强度 v3 (董哥建议: 涨停家数 + 连板数 + 连板高度 + 跌停家数 + 题材强度)

回算 D 日连板:
- D-N (5 天) 涨停股集合, 推断每只票截至 D 日连板数
- D 日 ≥2 板 = (D-1 涨停 ∩ D 涨停)
- D 日 ≥3 板 = (D-2 涨停 ∩ D-1 涨停 ∩ D 涨停)
- D 日跌停股
- 板块强度综合分

公式:
sector_score = zt_count × 1.0
             + lb2_count × 2.0  
             + lb3_count × 3.0
             + max_lbc × 5.0  (龙头加权)
             - dt_count × 1.5
             + persist_n28 × 0.5
"""
import json, time, urllib.request, math, re
from pathlib import Path
import pywencai
import warnings; warnings.filterwarnings('ignore')
from collections import defaultdict

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

EXCLUDE_SECTORS = {
    '融资融券', '沪股通', '深股通', '国企改革', '新股与次新股', 
    '上证A50', '上证180', '沪深300', '中证500', '中证1000',
    'ST板块', 'MSCI中国', '专精特新', '小盘股',
    '股权转让(并购重组)', '一带一路', '西部大开发',
}


def safe(v, default=0):
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except: return default


def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689') or code.startswith('8') or code.startswith('92')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


def is_dt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689') or code.startswith('8') or code.startswith('92')
    if is_st: return chg <= -4.7
    if is_20: return chg <= -19
    return chg <= -9.5


def get_chg(code, target):
    if code.startswith('8') or code.startswith('92'): return None
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        for i, b in enumerate(bars):
            if b[0] == target and i > 0:
                return (float(b[2]) - float(bars[i-1][2])) / float(bars[i-1][2]) * 100
    except: pass
    return None


def get_zt_set_concepts(d_str):
    """拉某天涨停股 + 所属概念: code -> {name, concepts[]}"""
    df = pywencai.get(query=f'{d_str} 涨停 所属概念', loop=True, timeout=120)
    if df is None or isinstance(df, dict) or len(df) == 0: return {}
    
    zt_data = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            concepts_str = str(row.get('所属概念', '') or '')
            if not code or not concepts_str: continue
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            zt_data[code] = {'name': name, 'concepts': concepts}
        except: continue
    return zt_data


def get_dt_set(d_str):
    """拉某天跌停股: code"""
    df = pywencai.get(query=f'{d_str} 跌停', loop=True, timeout=120)
    if df is None or isinstance(df, dict) or len(df) == 0: return set()
    return set(str(row.get('code', '')).strip() for _, row in df.iterrows() if row.get('code'))


def main():
    D = '2026-04-29'  # 测试日期
    D_PREV = '2026-04-28'  # D-1
    D_PREV2 = '2026-04-25'  # D-2 (但 4-25 周六, 所以是 4-24)
    D_PREV2 = '2026-04-24'  # 4-25 周六
    D_NEXT = '2026-04-30'  # D+1 (评估)
    
    print(f'🔬 板块强度 v3 (5 维: {D})', flush=True)
    
    # 1. 拉 D-2 / D-1 / D 涨停股 + 概念
    print(f'  拉 {D_PREV2} 涨停股...', flush=True)
    zt_d_prev2 = get_zt_set_concepts(D_PREV2)
    print(f'    {len(zt_d_prev2)} 只', flush=True)
    
    print(f'  拉 {D_PREV} 涨停股...', flush=True)
    zt_d_prev = get_zt_set_concepts(D_PREV)
    print(f'    {len(zt_d_prev)} 只', flush=True)
    
    print(f'  拉 {D} 涨停股...', flush=True)
    zt_d = get_zt_set_concepts(D)
    print(f'    {len(zt_d)} 只', flush=True)
    
    print(f'  拉 {D} 跌停股...', flush=True)
    dt_d = get_dt_set(D)
    print(f'    {len(dt_d)} 只', flush=True)
    
    # 2. 推断连板: D 日 ≥2 板 = D 涨停 ∩ D-1 涨停
    lb2_codes = set(zt_d) & set(zt_d_prev)  # ≥2 板
    lb3_codes = lb2_codes & set(zt_d_prev2)  # ≥3 板
    print(f'\n  D 日连板推断: ≥2板 {len(lb2_codes)}, ≥3板 {len(lb3_codes)}', flush=True)
    
    # 3. 板块统计 (5 维)
    sector_stats = defaultdict(lambda: {
        'zt_count': 0, 'zt_codes': [],
        'lb2_count': 0, 'lb2_codes': [],
        'lb3_count': 0, 'lb3_codes': [],
        'dt_count': 0, 'dt_codes': [],
        'persist_n_prev': 0,  # D-1 涨停数
    })
    
    for code, info in zt_d.items():
        for c in info['concepts']:
            sector_stats[c]['zt_count'] += 1
            sector_stats[c]['zt_codes'].append({'code': code, 'name': info['name']})
            if code in lb2_codes:
                sector_stats[c]['lb2_count'] += 1
                sector_stats[c]['lb2_codes'].append(code)
            if code in lb3_codes:
                sector_stats[c]['lb3_count'] += 1
                sector_stats[c]['lb3_codes'].append(code)
    
    for code, info in zt_d_prev.items():
        for c in info['concepts']:
            sector_stats[c]['persist_n_prev'] += 1
    
    # 推断每个板块的"龙头连板数" = 板块成员的最大连板
    # 简化: 用 lb3 count > 0 → max_lbc=3+, lb2 count > 0 → max_lbc=2, 否则 1
    for c, s in sector_stats.items():
        if s['lb3_count'] > 0: s['max_lbc'] = 3  # 至少 3
        elif s['lb2_count'] > 0: s['max_lbc'] = 2
        else: s['max_lbc'] = 1 if s['zt_count'] > 0 else 0
    
    # 拉跌停股的板块 — 但跌停查询里没有所属概念, 简化跳过 (大部分跌停是垃圾股, 板块影响小)
    
    # 4. 计算综合分
    for c, s in sector_stats.items():
        s['score'] = (s['zt_count'] * 1.0 + 
                     s['lb2_count'] * 2.0 + 
                     s['lb3_count'] * 3.0 + 
                     s['max_lbc'] * 5.0 + 
                     s['persist_n_prev'] * 0.5)
    
    # Top 板块
    print(f'\n=== Top 板块 (按综合分): ===', flush=True)
    sec_sorted = sorted(sector_stats.items(), key=lambda x: -x[1]['score'])
    print(f'  {"板块":<22} 涨停 ≥2板 ≥3板 龙头 D-1涨停 综合分', flush=True)
    for c, s in sec_sorted[:20]:
        print(f'  {c:<22} {s["zt_count"]:>4} {s["lb2_count"]:>4} {s["lb3_count"]:>4} {s["max_lbc"]:>4} {s["persist_n_prev"]:>5}   {s["score"]:>5.1f}', flush=True)
    
    # 5. 全市场候选 + 板块强度评分
    print(f'\n  拉 {D} 全市场...', flush=True)
    df_all = pywencai.get(query=f'{D} 涨跌幅 量比 收盘价 所属概念', loop=True, timeout=180)
    print(f'  全市场: {len(df_all)} 只', flush=True)
    
    candidates = []
    for _, row in df_all.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            if not code or 'ST' in name or '退' in name: continue
            chg = safe(row.get(f'涨跌幅:前复权[{D.replace("-", "")}]'))
            ratio = safe(row.get(f'量比[{D.replace("-", "")}]'))
            close = safe(row.get(f'收盘价:前复权[{D.replace("-", "")}]'))
            concepts_str = str(row.get('所属概念', '') or '')
            
            if close < 2 or close > 200: continue
            if chg < 0 or chg >= 9.5: continue  # 阳柱非涨停
            
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            
            # 取此票所属板块的最高分
            best_score = 0
            best_sec = None
            for c in concepts:
                s = sector_stats.get(c)
                if s and s['score'] > best_score:
                    best_score = s['score']
                    best_sec = c
            
            if not best_sec: continue
            
            best = sector_stats[best_sec]
            candidates.append({
                'code': code, 'name': name,
                'd0_chg': chg, 'volume_ratio': ratio,
                'best_sec': best_sec,
                'sec_score': best['score'],
                'sec_zt': best['zt_count'],
                'sec_lb2': best['lb2_count'],
                'sec_lb3': best['lb3_count'],
                'sec_max_lbc': best['max_lbc'],
                'sec_persist_prev': best['persist_n_prev'],
            })
        except: continue
    
    print(f'  有效候选: {len(candidates)}', flush=True)
    
    # 拉 D+1 涨幅
    sub = [c for c in candidates if c['volume_ratio'] >= 2]
    print(f'  量比≥2: {len(sub)} 只, 拉 {D_NEXT}...', flush=True)
    
    for i, c in enumerate(sub):
        chg = get_chg(c['code'], D_NEXT)
        c['chg_next'] = chg
        c['is_zt_next'] = is_zt(c['name'], chg, c['code']) if chg is not None else False
        if i % 50 == 0: print(f'    [{i}/{len(sub)}]...', flush=True)
        time.sleep(0.03)
    
    valid = [c for c in sub if c.get('chg_next') is not None]
    base = sum(1 for c in valid if c['is_zt_next']) / max(1, len(valid)) * 100
    fm_base = 2.7
    print(f'\n=== 基线: {sum(1 for c in valid if c["is_zt_next"])}/{len(valid)} = {base:.2f}%, lift {base/fm_base:.2f}x ===', flush=True)
    
    # 板块强度阈值
    print(f'\n=== H1: 板块综合分 ===', flush=True)
    for thr in [10, 20, 30, 40, 50, 60]:
        s = [c for c in valid if c['sec_score'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_next']) / len(s) * 100
            print(f'  sec_score≥{thr}: n={len(s):>4}, 涨停 {sum(1 for c in s if c["is_zt_next"])}, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H2: 板块连板数 (≥2 板) ===', flush=True)
    for thr in [1, 2, 3, 5]:
        s = [c for c in valid if c['sec_lb2'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_next']) / len(s) * 100
            print(f'  sec_lb2≥{thr}: n={len(s):>4}, 涨停 {sum(1 for c in s if c["is_zt_next"])}, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H3: 板块龙头连板高度 ===', flush=True)
    for thr in [2, 3]:
        s = [c for c in valid if c['sec_max_lbc'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_next']) / len(s) * 100
            print(f'  sec_max_lbc≥{thr}: n={len(s):>4}, 涨停 {sum(1 for c in s if c["is_zt_next"])}, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H4: 复合 ===', flush=True)
    for label, cond in [
        ('sec_score≥30 + 量比≥3', lambda c: c['sec_score']>=30 and c['volume_ratio']>=3),
        ('sec_score≥30 + 量比≥3 + d0_chg<5', lambda c: c['sec_score']>=30 and c['volume_ratio']>=3 and c['d0_chg']<5),
        ('sec_lb2≥2 + 量比≥3 + d0_chg<5', lambda c: c['sec_lb2']>=2 and c['volume_ratio']>=3 and c['d0_chg']<5),
        ('sec_max_lbc≥3 + 量比≥3', lambda c: c['sec_max_lbc']>=3 and c['volume_ratio']>=3),
        ('sec_max_lbc≥2 + sec_zt≥10 + 量比≥3', lambda c: c['sec_max_lbc']>=2 and c['sec_zt']>=10 and c['volume_ratio']>=3),
    ]:
        s = [c for c in valid if cond(c)]
        if s:
            r = sum(1 for c in s if c['is_zt_next']) / len(s) * 100
            zt_sym = ''
            zt_codes = [(c['code'], c['name']) for c in s if c['is_zt_next']]
            print(f'  {label}: n={len(s):>3}, 涨停 {sum(1 for c in s if c["is_zt_next"])}, lift {r/fm_base:.2f}x', flush=True)
            for code, n in zt_codes:
                print(f'      🚀 {code} {n}', flush=True)
    
    # 落档
    sec_data_serializable = {c: dict(s) for c, s in sec_sorted[:50]}
    out = WS / 'backtest' / f'sector_strength_v3_{D.replace("-","")}.json'
    with open(out, 'w') as f:
        json.dump({'top_sectors': sec_data_serializable, 'candidates': valid}, 
                  f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
