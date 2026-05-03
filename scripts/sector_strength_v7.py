#!/usr/bin/env python3
"""板块强度 v7 — 用真同花顺板块指数 (董哥建议)

核心改进:
- 板块涨幅 = 板块指数日 K 线涨幅 (不再估算)
- 板块量比 = 指数成交额 / 5 日均成交额
- 板块趋势 = 指数 5 日 / 10 日动量

数据源: akshare.stock_board_concept_index_ths (同花顺概念板块指数)
板块名: 与 wencai 一致 (验证 100% 匹配)

新维度 (来自真指数):
- idx_chg_d: 板块指数当天涨幅
- idx_chg_3d: 板块指数 3 日涨幅
- idx_chg_5d: 板块指数 5 日涨幅
- idx_vol_ratio: 当天成交额 / 5 日均
- idx_above_ma5: 收盘是否在 MA5 上 (动量)
- idx_above_ma10: 在 MA10 上 (中期趋势)

仍保留 v6 的:
- 涨停个数 + 连板梯队 + 龙头 max_lbc (个股聚合, 这部分指数没法替代)
- 跌停反向

综合分公式:
score = 涨停核心 (30 分) + 板块指数维度 (30 分) + 宽度 (15 分) - 退潮 (15 分)
"""
import json, time, urllib.request, math, re
from pathlib import Path
import pywencai
import akshare as ak
import warnings; warnings.filterwarnings('ignore')
from collections import defaultdict
import pandas as pd

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
    df = pywencai.get(query=f'{d_str} 涨跌幅 量比 收盘价 成交额 所属概念', loop=True, timeout=180)
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
            amount = safe(row.get(f'成交额[{yyyymmdd}]'))
            concepts_str = str(row.get('所属概念', '') or '')
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            data[code] = {'name': name, 'chg': chg, 'ratio': ratio, 
                         'close': close, 'amount': amount, 'concepts': concepts}
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


def get_sector_index_metrics(sec_name, sec_code, target_d):
    """拉板块指数, 算关键指标 (针对 target_d)
    
    返回:
      idx_chg_d: 当天涨幅
      idx_chg_3d: 3 日涨幅 (D - D-3)
      idx_chg_5d: 5 日涨幅
      idx_vol_ratio: 当天成交额 / 5 日均
      idx_above_ma5: 是否站上 MA5
      idx_above_ma10: 是否站上 MA10
    """
    target_d_yyyymmdd = target_d.replace('-', '')
    # 拉 30 天数据 (足够算 MA10)
    start = '20260401'
    end = '20260430'
    try:
        df = ak.stock_board_concept_index_ths(symbol=sec_name, start_date=start, end_date=end)
        if df is None or len(df) == 0: return None
        df['日期'] = pd.to_datetime(df['日期'])
        target_dt = pd.to_datetime(target_d)
        df = df[df['日期'] <= target_dt].sort_values('日期').reset_index(drop=True)
        if len(df) < 5: return None
        
        last = df.iloc[-1]
        if last['日期'].strftime('%Y-%m-%d') != target_d:
            return None  # 没有 target_d 数据
        
        # 涨幅
        prev = df.iloc[-2]
        idx_chg_d = (last['收盘价'] - prev['收盘价']) / prev['收盘价'] * 100
        
        # 3 日 / 5 日涨幅
        idx_chg_3d = idx_chg_5d = None
        if len(df) >= 4:
            d_3 = df.iloc[-4]
            idx_chg_3d = (last['收盘价'] - d_3['收盘价']) / d_3['收盘价'] * 100
        if len(df) >= 6:
            d_5 = df.iloc[-6]
            idx_chg_5d = (last['收盘价'] - d_5['收盘价']) / d_5['收盘价'] * 100
        
        # 成交额量比 (今天 / 5 日均)
        if len(df) >= 6:
            recent_5_avg = df.iloc[-6:-1]['成交额'].mean()  # 前 5 日均
            idx_vol_ratio = last['成交额'] / recent_5_avg if recent_5_avg else 0
        else:
            idx_vol_ratio = 0
        
        # MA5 / MA10
        idx_above_ma5 = idx_above_ma10 = False
        if len(df) >= 5:
            ma5 = df.iloc[-5:]['收盘价'].mean()
            idx_above_ma5 = last['收盘价'] > ma5
        if len(df) >= 10:
            ma10 = df.iloc[-10:]['收盘价'].mean()
            idx_above_ma10 = last['收盘价'] > ma10
        
        return {
            'idx_chg_d': idx_chg_d,
            'idx_chg_3d': idx_chg_3d if idx_chg_3d is not None else 0,
            'idx_chg_5d': idx_chg_5d if idx_chg_5d is not None else 0,
            'idx_vol_ratio': idx_vol_ratio,
            'idx_above_ma5': idx_above_ma5,
            'idx_above_ma10': idx_above_ma10,
            'idx_close': float(last['收盘价']),
        }
    except Exception as e:
        return None


def main():
    D = '2026-04-29'
    D1 = '2026-04-28'
    D2 = '2026-04-24'
    D3 = '2026-04-23'
    D_NEXT = '2026-04-30'
    
    print(f'🔬 板块强度 v7 — 真板块指数 ({D})\n', flush=True)
    
    # 1. 同花顺板块名 → code 映射
    print('  拉同花顺板块清单...', flush=True)
    ths_concepts = ak.stock_board_concept_name_ths()
    sec2code = dict(zip(ths_concepts['name'], ths_concepts['code']))
    print(f'    {len(sec2code)} 个板块', flush=True)
    
    # 2. 拉历史涨停 + 全市场
    print(f'  拉历史涨停...', flush=True)
    zt_d3 = get_zt_concepts(D3); print(f'    D-3: {len(zt_d3)}', flush=True)
    zt_d2 = get_zt_concepts(D2); print(f'    D-2: {len(zt_d2)}', flush=True)
    zt_d1 = get_zt_concepts(D1); print(f'    D-1: {len(zt_d1)}', flush=True)
    zt_d  = get_zt_concepts(D);  print(f'    D: {len(zt_d)}', flush=True)
    print(f'  拉跌停 + 全市场...', flush=True)
    dt_d = get_dt_concepts(D)
    market_d = get_market(D); print(f'    全市场: {len(market_d)}', flush=True)
    
    # 大盘均涨幅 (用于 alpha 但这次先不需要)
    market_chgs = [info['chg'] for info in market_d.values() if info['chg'] is not None]
    market_avg_chg = sum(market_chgs) / len(market_chgs) if market_chgs else 0
    print(f'  大盘平均涨幅: {market_avg_chg:+.2f}%', flush=True)
    
    # 3. 推断连板
    lb2 = set(zt_d) & set(zt_d1)
    lb3 = lb2 & set(zt_d2)
    lb4 = lb3 & set(zt_d3)
    print(f'  连板: ≥2板 {len(lb2)}, ≥3板 {len(lb3)}, ≥4板 {len(lb4)}', flush=True)
    
    # 4. 板块成员 (从 wencai)
    sector_members = defaultdict(set)
    for code, info in market_d.items():
        for c in info['concepts']:
            sector_members[c].add(code)
    
    # 5. 计算每个板块 (只算 wencai+ths 都有的)
    print(f'\n  计算板块强度 (只处理 wencai∩ths 的板块)...', flush=True)
    valid_sectors = [s for s in sector_members if s in sec2code and len(sector_members[s]) >= 5]
    print(f'  有效板块: {len(valid_sectors)} (wencai 总 {len(sector_members)})', flush=True)
    
    sector_stats = {}
    for i, sec in enumerate(valid_sectors):
        members = sector_members[sec]
        zt_d_codes = [c for c in members if c in zt_d]
        zt_d1_codes = [c for c in members if c in zt_d1]
        
        zt_d_n = len(zt_d_codes)
        lb2_n = len([c for c in zt_d_codes if c in lb2])
        lb3_n = len([c for c in zt_d_codes if c in lb3])
        lb4_n = len([c for c in zt_d_codes if c in lb4])
        max_lbc = 4 if lb4_n else (3 if lb3_n else (2 if lb2_n else (1 if zt_d_n else 0)))
        dt_d_n = len([c for c in members if c in dt_d])
        flip_dt = len([c for c in zt_d1_codes if c in dt_d])
        
        # 宽度 (个股聚合)
        chgs = [market_d[c]['chg'] for c in members if c in market_d and market_d[c]['chg'] is not None]
        if chgs:
            up_ratio = sum(1 for x in chgs if x > 0) / len(chgs)
            ge5_ratio = sum(1 for x in chgs if x >= 5) / len(chgs)
            ge7_ratio = sum(1 for x in chgs if x >= 7) / len(chgs)
        else:
            up_ratio = ge5_ratio = ge7_ratio = 0
        
        # **真板块指数** (只要算最重要的几个)
        if zt_d_n >= 2 or len(zt_d1_codes) >= 2:  # 只对有热度的板块拉指数 (省时间)
            idx = get_sector_index_metrics(sec, sec2code[sec], D)
        else:
            idx = None
        
        # 综合分
        score = (
            # 涨停核心 (30 分)
            zt_d_n * 1.0 +
            lb2_n * 2.0 +
            lb3_n * 4.0 +
            max_lbc * 5.0 +
            len(zt_d1_codes) * 0.5 +
            
            # 板块指数 (30 分)
            (idx['idx_chg_d'] if idx else 0) * 2.0 +  # 1% = 2 分
            (idx['idx_chg_3d'] if idx else 0) * 1.0 +  # 3 日涨幅
            (idx['idx_vol_ratio'] - 1 if idx and idx['idx_vol_ratio'] else 0) * 5.0 +  # 量比放大 1.5 = 2.5 分
            (5 if idx and idx['idx_above_ma5'] else 0) +
            (5 if idx and idx['idx_above_ma10'] else 0) +
            
            # 宽度 (15 分)
            ge5_ratio * 100 * 0.3 +
            ge7_ratio * 100 * 0.5 +
            up_ratio * 100 * 0.05 -
            
            # 退潮 (-15 极限)
            dt_d_n * 2.0 -
            flip_dt * 5.0
        )
        
        sector_stats[sec] = {
            'sec': sec, 'sec_code': sec2code[sec],
            'members_n': len(members),
            'zt_d': zt_d_n, 'zt_d1': len(zt_d1_codes),
            'lb2': lb2_n, 'lb3': lb3_n, 'lb4': lb4_n, 'max_lbc': max_lbc,
            'up_ratio': up_ratio, 'ge5_ratio': ge5_ratio, 'ge7_ratio': ge7_ratio,
            'dt_d': dt_d_n, 'flip_dt': flip_dt,
            'idx': idx,
            'score': score,
        }
        
        if (i+1) % 30 == 0:
            print(f'    [{i+1}/{len(valid_sectors)}]...', flush=True)
        time.sleep(0.05)  # akshare 限速
    
    # 排序
    sec_sorted = sorted(sector_stats.items(), key=lambda x: -x[1]['score'])
    
    print(f'\n=== Top 25 板块 (按 v7 综合分, 用真指数) ===', flush=True)
    print(f'  {"板块":<18} ZT D-1 ≥2 ≥3 ≥4 龙头 IdxD% Idx3D% IdxVol Ma5 Ma10 ≥5% ≥7% 跌停 综合分', flush=True)
    for sec, s in sec_sorted[:25]:
        idx = s.get('idx') or {}
        idx_d = idx.get('idx_chg_d', 0)
        idx_3d = idx.get('idx_chg_3d', 0)
        idx_vr = idx.get('idx_vol_ratio', 0)
        ma5 = '✓' if idx.get('idx_above_ma5') else ' '
        ma10 = '✓' if idx.get('idx_above_ma10') else ' '
        print(f'  {sec:<18} {s["zt_d"]:>3} {s["zt_d1"]:>3} {s["lb2"]:>2} {s["lb3"]:>2} {s["lb4"]:>2} {s["max_lbc"]:>3} {idx_d:>+5.2f} {idx_3d:>+6.2f} {idx_vr:>5.2f}  {ma5}  {ma10}  {s["ge5_ratio"]*100:>4.1f} {s["ge7_ratio"]*100:>4.1f} {s["dt_d"]:>3} {s["score"]:>+6.1f}', flush=True)
    
    # 4-30 命中股板块排名
    print(f'\n=== 4-30 命中股板块排名 ===', flush=True)
    targets = ['688400', '300885', '603711', '603360']
    for code in targets:
        info = market_d.get(code)
        if not info: continue
        best_sec, best_score = None, -1e9
        for c in info['concepts']:
            sp = sector_stats.get(c)
            if sp and sp['score'] > best_score:
                best_score = sp['score']; best_sec = c
        rank = next((i for i, (s, _) in enumerate(sec_sorted) if s == best_sec), -1) + 1
        idx_str = ''
        if best_sec and sector_stats[best_sec].get('idx'):
            idx = sector_stats[best_sec]['idx']
            idx_str = f' (Idx D%={idx["idx_chg_d"]:+.2f} 3D%={idx["idx_chg_3d"]:+.2f} VR={idx["idx_vol_ratio"]:.2f} MA5={"✓" if idx["idx_above_ma5"] else "✗"})'
        print(f'  {code} {info["name"]}: 板块={best_sec} 综合分={best_score:.1f} 排名 {rank}{idx_str}', flush=True)
    
    # 候选评估
    candidates = []
    for code, info in market_d.items():
        if info['close'] < 2 or info['close'] > 200: continue
        if 'ST' in info['name'] or '退' in info['name']: continue
        if info['chg'] is None or info['chg'] < 0: continue
        
        best_sec, best_score = None, -1e9
        max_lbc = 0; sec_zt_d = 0
        idx = None
        for c in info['concepts']:
            sp = sector_stats.get(c)
            if sp and sp['score'] > best_score:
                best_score = sp['score']; best_sec = c
                max_lbc = sp['max_lbc']
                sec_zt_d = sp['zt_d']
                idx = sp.get('idx')
        if best_sec is None: continue
        candidates.append({
            'code': code, 'name': info['name'],
            'd0_chg': info['chg'], 'volume_ratio': info['ratio'],
            'best_sec': best_sec, 'sec_score': best_score,
            'sec_max_lbc': max_lbc, 'sec_zt_d': sec_zt_d,
            'idx_chg_d': idx['idx_chg_d'] if idx else 0,
            'idx_above_ma5': idx['idx_above_ma5'] if idx else False,
            'idx_vol_ratio': idx['idx_vol_ratio'] if idx else 0,
            'is_zt_d0': info['chg'] >= 9.5,
        })
    
    sub = [c for c in candidates if c['volume_ratio'] >= 2 and not c['is_zt_d0']]
    print(f'\n  量比≥2 + 非D涨停: {len(sub)} 只, 拉 {D_NEXT}...', flush=True)
    
    for i, c in enumerate(sub):
        chg = get_chg_next(c['code'], D_NEXT)
        c['chg_next'] = chg
        c['is_zt_next'] = is_zt(c['name'], chg, c['code']) if chg is not None else False
        if i % 50 == 0 and i: print(f'    [{i}/{len(sub)}]...', flush=True)
        time.sleep(0.03)
    
    valid = [c for c in sub if c.get('chg_next') is not None]
    fm_base = 2.7
    
    print(f'\n=== 阈值 sec_score ===', flush=True)
    for thr in [20, 30, 40, 50, 60, 70, 80, 90]:
        s = [c for c in valid if c['sec_score'] >= thr]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s)
            print(f'  sec_score>={thr}: n={len(s)}, zt={zt}, lift={r/fm_base:.2f}x', flush=True)
    
    print('\n=== composite (with real index) ===', flush=True)
    composites = [
        ('sec_score>=40 + ratio>=3', lambda c: c['sec_score']>=40 and c['volume_ratio']>=3),
        ('sec_score>=50 + ratio>=3', lambda c: c['sec_score']>=50 and c['volume_ratio']>=3),
        ('sec_score>=60 + ratio>=3', lambda c: c['sec_score']>=60 and c['volume_ratio']>=3),
        ('sec_score>=70 + ratio>=3', lambda c: c['sec_score']>=70 and c['volume_ratio']>=3),
        ('max_lbc>=3 + zt_d>=10 + ratio>=2', lambda c: c['sec_max_lbc']>=3 and c['sec_zt_d']>=10 and c['volume_ratio']>=2),
        ('idx_chg>0 + idx_ma5 + ratio>=3', lambda c: c['idx_chg_d']>0 and c['idx_above_ma5'] and c['volume_ratio']>=3),
        ('idx_chg>=1 + idx_vol>=1.2 + ratio>=3', lambda c: c['idx_chg_d']>=1 and c['idx_vol_ratio']>=1.2 and c['volume_ratio']>=3),
        ('idx_chg>=1 + idx_ma5 + max_lbc>=2 + ratio>=3', lambda c: c['idx_chg_d']>=1 and c['idx_above_ma5'] and c['sec_max_lbc']>=2 and c['volume_ratio']>=3),
        ('sec_score>=50 + idx_ma5 + ratio>=2', lambda c: c['sec_score']>=50 and c['idx_above_ma5'] and c['volume_ratio']>=2),
        ('sec_score>=40 + idx_chg_d>=1 + ratio>=2 + d0_chg<5', lambda c: c['sec_score']>=40 and c['idx_chg_d']>=1 and c['volume_ratio']>=2 and c['d0_chg']<5),
    ]
    for label, cond in composites:
        s = [c for c in valid if cond(c)]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s)
            print(f'  {label}: n={len(s)}, zt={zt}, lift={r/fm_base:.2f}x', flush=True)
            for c in s:
                if c['is_zt_next']:
                    print(f'      ZT {c["code"]} {c["name"]} sec={c["best_sec"]} idxD={c["idx_chg_d"]:+.2f}', flush=True)
    
    out = WS / 'backtest' / f'sector_strength_v7_{D.replace("-","")}.json'
    sec_data = {sec: dict(s) for sec, s in sec_sorted[:50]}
    with open(out, 'w') as f:
        json.dump({'top_sectors': sec_data, 'candidates': valid, 'market_avg_chg': market_avg_chg}, 
                  f, ensure_ascii=False, indent=2, default=str)
    print(f'\nsave: {out}', flush=True)


if __name__ == '__main__':
    main()
