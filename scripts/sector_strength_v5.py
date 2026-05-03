#!/usr/bin/env python3
"""板块强度 v5 — 融合 v3 (连板) + v4 (热度趋势) 长处

v3 优点: max_lbc (龙头连板高度) 是最有区分度的特征
v4 优点: 多日热度趋势 + 资金活跃度

v5 公式:
sector_score = 涨停家数 × 1.0
             + ≥2 板数 × 2.0  
             + ≥3 板数 × 4.0
             + 龙头连板高度 × 6.0  ⭐ (主要)
             + 趋势分 × 3.0  (D-3..D 累积涨停增加)
             + 平均量比 × 2.0  (>1 为正)
             - 跌停数 × 2.0
             + D-1 涨停数 × 0.5

测试日期: 4-29 → 4-30
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


def get_zt_concepts(d_str):
    df = pywencai.get(query=f'{d_str} 涨停 所属概念', loop=True, timeout=120)
    if df is None or isinstance(df, dict): return {}
    data = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            concepts_str = str(row.get('所属概念', '') or '')
            if not code: continue
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            data[code] = {'name': name, 'concepts': concepts}
        except: continue
    return data


def get_dt_concepts(d_str):
    df = pywencai.get(query=f'{d_str} 跌停 所属概念', loop=True, timeout=120)
    if df is None or isinstance(df, dict): return {}
    data = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            concepts_str = str(row.get('所属概念', '') or '')
            if not code: continue
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            data[code] = {'concepts': concepts}
        except: continue
    return data


def get_market(d_str):
    yyyymmdd = d_str.replace('-', '')
    df = pywencai.get(query=f'{d_str} 涨跌幅 量比 收盘价 所属概念', loop=True, timeout=180)
    if df is None or isinstance(df, dict): return {}
    data = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            if not code: continue
            chg = safe(row.get(f'涨跌幅:前复权[{yyyymmdd}]'))
            ratio = safe(row.get(f'量比[{yyyymmdd}]'))
            close = safe(row.get(f'收盘价:前复权[{yyyymmdd}]'))
            concepts_str = str(row.get('所属概念', '') or '')
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            data[code] = {'name': name, 'chg': chg, 'ratio': ratio, 'close': close, 'concepts': concepts}
        except: continue
    return data


def get_chg_next(code, target):
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


def main():
    D = '2026-04-29'
    D1 = '2026-04-28'
    D2 = '2026-04-24'
    D3 = '2026-04-23'
    D_NEXT = '2026-04-30'
    
    print(f'🔬 板块强度 v5 — v3+v4 融合 ({D})\n', flush=True)
    
    # 拉数据
    print('  拉历史涨停 (4 天)...', flush=True)
    zt_d3 = get_zt_concepts(D3); print(f'    D-3 ({D3}): {len(zt_d3)} 只', flush=True)
    zt_d2 = get_zt_concepts(D2); print(f'    D-2 ({D2}): {len(zt_d2)} 只', flush=True)
    zt_d1 = get_zt_concepts(D1); print(f'    D-1 ({D1}): {len(zt_d1)} 只', flush=True)
    zt_d  = get_zt_concepts(D);  print(f'    D ({D}): {len(zt_d)} 只', flush=True)
    
    print('  拉跌停 + 全市场...', flush=True)
    dt_d = get_dt_concepts(D); print(f'    跌停: {len(dt_d)} 只', flush=True)
    market_d = get_market(D); print(f'    全市场: {len(market_d)} 只', flush=True)
    
    # 推断连板
    lb2 = set(zt_d) & set(zt_d1)  # ≥2 板
    lb3 = lb2 & set(zt_d2)         # ≥3 板
    lb4 = lb3 & set(zt_d3)         # ≥4 板
    print(f'  连板推断: ≥2板 {len(lb2)}, ≥3板 {len(lb3)}, ≥4板 {len(lb4)}', flush=True)
    
    # 计算每个板块强度
    sector_stats = defaultdict(lambda: {
        'zt_d': 0, 'zt_d1': 0, 'zt_d2': 0, 'zt_d3': 0,
        'lb2': 0, 'lb3': 0, 'lb4': 0,
        'dt_d': 0,
        'members': set(), 
        'sum_chg': 0, 'n_chg': 0, 'sum_ratio': 0, 'n_ratio': 0,
    })
    
    # 涨停按板块累计
    for code, info in zt_d.items():
        for c in info['concepts']:
            sector_stats[c]['zt_d'] += 1
            if code in lb2: sector_stats[c]['lb2'] += 1
            if code in lb3: sector_stats[c]['lb3'] += 1
            if code in lb4: sector_stats[c]['lb4'] += 1
    for zt_dict, key in [(zt_d1, 'zt_d1'), (zt_d2, 'zt_d2'), (zt_d3, 'zt_d3')]:
        for code, info in zt_dict.items():
            for c in info['concepts']:
                sector_stats[c][key] += 1
    for code, info in dt_d.items():
        for c in info['concepts']:
            sector_stats[c]['dt_d'] += 1
    
    # 板块成员 + 平均涨幅 + 平均量比
    for code, info in market_d.items():
        for c in info['concepts']:
            sector_stats[c]['members'].add(code)
            if info['chg'] is not None and not math.isnan(info['chg']):
                sector_stats[c]['sum_chg'] += info['chg']
                sector_stats[c]['n_chg'] += 1
            if info['ratio'] is not None and not math.isnan(info['ratio']):
                sector_stats[c]['sum_ratio'] += info['ratio']
                sector_stats[c]['n_ratio'] += 1
    
    # 算板块综合分
    for sec, s in sector_stats.items():
        # max_lbc
        if s['lb4'] > 0: s['max_lbc'] = 4
        elif s['lb3'] > 0: s['max_lbc'] = 3
        elif s['lb2'] > 0: s['max_lbc'] = 2
        else: s['max_lbc'] = 1 if s['zt_d'] > 0 else 0
        
        # 趋势分
        zt_seq = [s['zt_d3'], s['zt_d2'], s['zt_d1'], s['zt_d']]
        trend_raw = zt_seq[3] - zt_seq[0]
        s['trend_score'] = max(-2, min(3, trend_raw // 3))  # 每多 3 个涨停 +1, 上限 3, 下限 -2
        
        # 平均涨幅 / 平均量比
        s['avg_chg'] = s['sum_chg'] / s['n_chg'] if s['n_chg'] else 0
        s['avg_ratio'] = s['sum_ratio'] / s['n_ratio'] if s['n_ratio'] else 0
        s['members_n'] = len(s['members'])
        
        # 综合分
        s['score'] = (
            s['zt_d'] * 1.0 +
            s['lb2'] * 2.0 +
            s['lb3'] * 4.0 +
            s['max_lbc'] * 6.0 +
            s['trend_score'] * 3.0 +
            (s['avg_ratio'] - 1.0) * 2.0 +  # 量比基线 1.0
            s['avg_chg'] * 0.5 -  # 平均涨幅每 1% +0.5
            s['dt_d'] * 2.0 +
            s['zt_d1'] * 0.5
        )
    
    # 排序输出
    sec_sorted = sorted(sector_stats.items(), key=lambda x: -x[1]['score'])
    print(f'\n=== Top 20 板块 (按 v5 综合分) ===', flush=True)
    print(f'  {"板块":<20} 成员 涨停D D-1 D-2 D-3 ≥2 ≥3 ≥4 龙头 趋势 平涨% 平量比 跌停 综合分', flush=True)
    for sec, s in sec_sorted[:20]:
        print(f'  {sec:<20} {s["members_n"]:>3} {s["zt_d"]:>4}  {s["zt_d1"]:>3} {s["zt_d2"]:>3} {s["zt_d3"]:>3} {s["lb2"]:>2} {s["lb3"]:>2} {s["lb4"]:>2} {s["max_lbc"]:>3} {s["trend_score"]:>+3} {s["avg_chg"]:>+5.2f} {s["avg_ratio"]:>5.2f} {s["dt_d"]:>3} {s["score"]:>+6.1f}', flush=True)
    
    # 4-30 命中股板块排名
    print(f'\n=== 4-30 命中股 板块排名 ===', flush=True)
    targets = ['688400', '300885', '603711', '603360']
    for code in targets:
        info = market_d.get(code)
        if not info: 
            print(f'  {code}: 不在市场 (可能是涨停)')
            continue
        best_sec, best_score = None, -1e9
        for c in info['concepts']:
            sp = sector_stats.get(c)
            if sp and sp['score'] > best_score:
                best_score = sp['score']
                best_sec = c
        rank = next((i for i, (s, _) in enumerate(sec_sorted) if s == best_sec), -1) + 1
        print(f'  {code} {info["name"]}: 板块={best_sec} 综合分={best_score:.1f} 排名 {rank}', flush=True)
    
    # 候选 + 评估
    candidates = []
    for code, info in market_d.items():
        if info['close'] < 2 or info['close'] > 200: continue
        if 'ST' in info['name'] or '退' in info['name']: continue
        if info['chg'] is None or info['chg'] < 0: continue
        # 不要过滤 D 涨停 (后面只看 D+1)
        
        best_sec, best_score = None, -1e9
        max_lbc = 0
        zt_d_count = 0
        for c in info['concepts']:
            sp = sector_stats.get(c)
            if sp and sp['score'] > best_score:
                best_score = sp['score']
                best_sec = c
                max_lbc = sp['max_lbc']
                zt_d_count = sp['zt_d']
        
        if best_sec is None: continue
        candidates.append({
            'code': code, 'name': info['name'],
            'd0_chg': info['chg'], 'volume_ratio': info['ratio'],
            'best_sec': best_sec, 'sec_score': best_score,
            'sec_max_lbc': max_lbc, 'sec_zt_d': zt_d_count,
            'is_zt_d0': info['chg'] >= 9.5,
        })
    
    # 拉 D+1 涨幅 (只看非 D 涨停 + 量比 >= 2)
    sub = [c for c in candidates if c['volume_ratio'] >= 2 and not c['is_zt_d0']]
    print(f'\n  量比≥2 + 非 D 涨停: {len(sub)} 只, 拉 {D_NEXT}...', flush=True)
    
    for i, c in enumerate(sub):
        chg = get_chg_next(c['code'], D_NEXT)
        c['chg_next'] = chg
        c['is_zt_next'] = is_zt(c['name'], chg, c['code']) if chg is not None else False
        if i % 50 == 0 and i: print(f'    [{i}/{len(sub)}]...', flush=True)
        time.sleep(0.03)
    
    valid = [c for c in sub if c.get('chg_next') is not None]
    fm_base = 2.7
    
    print(f'\n=== 综合分 阈值测试 ===', flush=True)
    for thr in [10, 20, 30, 40, 50, 60, 70]:
        s = [c for c in valid if c['sec_score'] >= thr]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s)
            print(f'  sec_score≥{thr:>3}: n={len(s):>4}, 涨停 {zt}, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== 复合条件 ===', flush=True)
    for label, cond in [
        ('sec_max_lbc≥3 + 量比≥3', lambda c: c['sec_max_lbc']>=3 and c['volume_ratio']>=3),
        ('sec_max_lbc≥3 + 量比≥3 + d0_chg<8', lambda c: c['sec_max_lbc']>=3 and c['volume_ratio']>=3 and c['d0_chg']<8),
        ('sec_score≥40 + 量比≥3', lambda c: c['sec_score']>=40 and c['volume_ratio']>=3),
        ('sec_score≥50 + 量比≥3', lambda c: c['sec_score']>=50 and c['volume_ratio']>=3),
        ('sec_score≥40 + 量比≥3 + d0_chg<5', lambda c: c['sec_score']>=40 and c['volume_ratio']>=3 and c['d0_chg']<5),
        ('sec_score≥40 + 量比≥2 + d0_chg<5', lambda c: c['sec_score']>=40 and c['volume_ratio']>=2 and c['d0_chg']<5),
        ('sec_max_lbc≥3 + sec_zt_d≥10 + 量比≥2', lambda c: c['sec_max_lbc']>=3 and c['sec_zt_d']>=10 and c['volume_ratio']>=2),
    ]:
        s = [c for c in valid if cond(c)]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s)
            print(f'  {label}: n={len(s):>3}, 涨停 {zt}, lift {r/fm_base:.2f}x', flush=True)
            for c in s:
                if c['is_zt_next']:
                    print(f'      🚀 {c["code"]} {c["name"]} sec={c["best_sec"]} score={c["sec_score"]:.1f}')
    
    # 落档
    out = WS / 'backtest' / f'sector_strength_v5_{D.replace("-","")}.json'
    sec_data = {}
    for sec, s in sec_sorted[:50]:
        s_clean = {k: v for k, v in s.items() if k != 'members'}
        s_clean['members_n'] = len(s.get('members', []))
        sec_data[sec] = s_clean
    with open(out, 'w') as f:
        json.dump({'top_sectors': sec_data, 'candidates': valid}, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
