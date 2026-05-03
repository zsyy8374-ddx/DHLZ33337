#!/usr/bin/env python3
"""板块强度 v6 — 完整 8 维模型

新增维度 (董哥建议 + 我补充):
A. 板块涨幅 (成交额加权) — 主力资金真实流向
B. 板块量比 (成交额加权) — 资金活跃度
C. 板块成交额放量倍数 — 今日 / 5 日均
D. 宽度: ≥5% / ≥7% / ≥9% 涨幅占比 — 真热度 vs 假热度
E. 连板梯队 (≥2/≥3/≥4/≥5)
F. 跌停反向 (含昨涨今跌)
G. 趋势斜率 (4 天涨停数变化)
H. 板块强度 vs 大盘 (alpha 超额)

权重调优思路: 
- 龙头连板高度仍是最强信号 (×6.0)
- 加权涨幅 ≥3% × 4.0
- 宽度 (≥5% 占比) ≥30% × 3.0
- 主升宽度 (≥7% 占比) ≥10% × 4.0
- 资金活跃 (加权量比 ≥1.3) × 2.0
- 连板梯队完整 (≥2≥3≥4 全有) × 2.0
- 跌停 × -2.0
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


def get_market_full(d_str):
    """全市场: 个股涨幅 + 量比 + 成交额"""
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


def compute_sector_v6(d, d1, d2, d3):
    """v6 完整板块强度计算"""
    # 拉数据
    print(f'  拉历史 4 天涨停...', flush=True)
    zt_d3 = get_zt_concepts(d3); print(f'    D-3: {len(zt_d3)}', flush=True)
    zt_d2 = get_zt_concepts(d2); print(f'    D-2: {len(zt_d2)}', flush=True)
    zt_d1 = get_zt_concepts(d1); print(f'    D-1: {len(zt_d1)}', flush=True)
    zt_d  = get_zt_concepts(d);  print(f'    D: {len(zt_d)}', flush=True)
    
    print(f'  拉跌停 + 全市场...', flush=True)
    dt_d = get_dt_concepts(d); print(f'    跌停: {len(dt_d)}', flush=True)
    market_d = get_market_full(d); print(f'    全市场: {len(market_d)}', flush=True)
    
    # 大盘平均涨幅 (用于 alpha 计算)
    market_chgs = [info['chg'] for info in market_d.values() if info['chg'] is not None]
    market_avg_chg = sum(market_chgs) / len(market_chgs) if market_chgs else 0
    print(f'  大盘平均涨幅: {market_avg_chg:+.2f}%', flush=True)
    
    # 推断连板梯队
    lb2 = set(zt_d) & set(zt_d1)
    lb3 = lb2 & set(zt_d2)
    lb4 = lb3 & set(zt_d3)
    print(f'  连板: ≥2板 {len(lb2)}, ≥3板 {len(lb3)}, ≥4板 {len(lb4)}', flush=True)
    
    # 板块成员
    sector_members = defaultdict(set)
    for code, info in market_d.items():
        for c in info['concepts']:
            sector_members[c].add(code)
    
    # 计算每个板块的所有维度
    sector_stats = {}
    for sec, members in sector_members.items():
        if len(members) < 5: continue  # 太小的板块跳过
        
        # === A. 涨停统计 ===
        zt_d_codes = [c for c in members if c in zt_d]
        zt_d1_codes = [c for c in members if c in zt_d1]
        zt_d2_codes = [c for c in members if c in zt_d2]
        zt_d3_codes = [c for c in members if c in zt_d3]
        
        zt_d_n = len(zt_d_codes)
        lb2_n = len([c for c in zt_d_codes if c in lb2])
        lb3_n = len([c for c in zt_d_codes if c in lb3])
        lb4_n = len([c for c in zt_d_codes if c in lb4])
        max_lbc = 4 if lb4_n else (3 if lb3_n else (2 if lb2_n else (1 if zt_d_n else 0)))
        
        # === B. 跌停 ===
        dt_d_n = len([c for c in members if c in dt_d])
        # 昨涨今跌
        flip_dt = len([c for c in zt_d1_codes if c in dt_d])
        
        # === C. 板块涨幅 (加权 + 平均) ===
        chgs = []
        amounts = []
        ratios = []
        for c in members:
            info = market_d.get(c)
            if info is None: continue
            if info['chg'] is not None: chgs.append(info['chg'])
            if info['amount']: amounts.append(info['amount'])
            if info['ratio'] is not None: ratios.append(info['ratio'])
        
        # 平均涨幅
        avg_chg = sum(chgs) / len(chgs) if chgs else 0
        # 加权涨幅 (按成交额)
        chg_amt_pairs = [(market_d[c]['chg'], market_d[c]['amount']) 
                        for c in members if c in market_d 
                        and market_d[c]['chg'] is not None 
                        and market_d[c]['amount']]
        if chg_amt_pairs:
            tot_amt = sum(a for _, a in chg_amt_pairs)
            weighted_chg = sum(c*a for c, a in chg_amt_pairs) / tot_amt if tot_amt else 0
        else:
            weighted_chg = avg_chg
        
        # 板块总成交额
        total_amount = sum(amounts) if amounts else 0
        avg_member_amount = total_amount / len(members) if len(members) else 0
        
        # === D. 板块量比 (加权) ===
        avg_ratio = sum(ratios) / len(ratios) if ratios else 0
        ratio_amt_pairs = [(market_d[c]['ratio'], market_d[c]['amount']) 
                          for c in members if c in market_d 
                          and market_d[c]['ratio'] is not None 
                          and market_d[c]['amount']]
        if ratio_amt_pairs:
            tot_amt = sum(a for _, a in ratio_amt_pairs)
            weighted_ratio = sum(r*a for r, a in ratio_amt_pairs) / tot_amt if tot_amt else 0
        else:
            weighted_ratio = avg_ratio
        
        # === E. 宽度 (上涨家数占比) ===
        n_total = len(chgs)
        if n_total:
            up_ratio = sum(1 for x in chgs if x > 0) / n_total
            ge5_ratio = sum(1 for x in chgs if x >= 5) / n_total  # 主升早期
            ge7_ratio = sum(1 for x in chgs if x >= 7) / n_total  # 主升期
            ge9_ratio = sum(1 for x in chgs if x >= 9.5) / n_total  # 涨停占比
        else:
            up_ratio = ge5_ratio = ge7_ratio = ge9_ratio = 0
        
        # === F. 趋势斜率 ===
        zt_seq = [len(zt_d3_codes), len(zt_d2_codes), len(zt_d1_codes), zt_d_n]
        # 简单线性: D - D-3
        trend_raw = zt_seq[3] - zt_seq[0]
        # 归一化 (按板块大小调整)
        trend_norm = trend_raw / max(5, len(members) ** 0.5)
        trend_score = max(-2, min(3, int(trend_norm * 5)))  # 调比例
        
        # === G. Alpha (vs 大盘) ===
        alpha = weighted_chg - market_avg_chg
        
        # === H. 综合分 ===
        score = (
            # 涨停核心 (40 满分)
            zt_d_n * 1.0 +
            lb2_n * 2.0 +
            lb3_n * 4.0 +
            lb4_n * 6.0 +
            max_lbc * 6.0 +
            # 板块涨幅 (15 满分)
            weighted_chg * 1.5 +  # 加权涨幅, 1% = 1.5 分
            alpha * 1.0 +  # 超大盘部分加分
            # 宽度 (15 满分)
            ge5_ratio * 100 * 0.3 +  # ≥5% 占比每 1% +0.3
            ge7_ratio * 100 * 0.5 +  # ≥7% 占比每 1% +0.5
            up_ratio * 100 * 0.05 +  # 上涨占比每 1% +0.05
            # 资金活跃 (5 满分)
            (weighted_ratio - 1) * 3 +  # 加权量比, 1.0 基线
            # 趋势 (10 满分)
            trend_score * 3 +
            # D-1 持续 (5 满分)
            len(zt_d1_codes) * 0.5 -
            # 退潮 (-15 极限)
            dt_d_n * 2.0 -
            flip_dt * 5.0  # 昨涨今跌严重
        )
        
        sector_stats[sec] = {
            'sec': sec, 'members_n': len(members),
            # 涨停
            'zt_d': zt_d_n, 'zt_d1': len(zt_d1_codes), 'zt_d2': len(zt_d2_codes), 'zt_d3': len(zt_d3_codes),
            'lb2': lb2_n, 'lb3': lb3_n, 'lb4': lb4_n, 'max_lbc': max_lbc,
            # 涨幅
            'avg_chg': avg_chg, 'weighted_chg': weighted_chg, 'alpha': alpha,
            # 宽度
            'up_ratio': up_ratio, 'ge5_ratio': ge5_ratio, 'ge7_ratio': ge7_ratio, 'ge9_ratio': ge9_ratio,
            # 量能
            'avg_ratio': avg_ratio, 'weighted_ratio': weighted_ratio, 'total_amount': total_amount,
            # 趋势
            'zt_seq': zt_seq, 'trend_raw': trend_raw, 'trend_score': trend_score,
            # 反向
            'dt_d': dt_d_n, 'flip_dt': flip_dt,
            # 综合
            'score': score,
        }
    
    return sector_stats, market_d, market_avg_chg


def main():
    D = '2026-04-29'
    D1 = '2026-04-28'
    D2 = '2026-04-24'
    D3 = '2026-04-23'
    D_NEXT = '2026-04-30'
    
    print(f'🔬 板块强度 v6 — 完整 8 维 ({D})\n', flush=True)
    
    sec_stats, market_d, mkt_avg = compute_sector_v6(D, D1, D2, D3)
    
    # Top 30 板块
    sec_sorted = sorted(sec_stats.items(), key=lambda x: -x[1]['score'])
    print(f'\n=== Top 25 板块 ({len(sec_stats)} 总数) ===', flush=True)
    print(f'  {"板块":<18} 成员 ZTD D-1 D-2 D-3 ≥2 ≥3 ≥4 龙头  加权% Alpha  ≥5% ≥7%  加权量 趋势 跌停 综合分', flush=True)
    for sec, s in sec_sorted[:25]:
        print(f'  {sec:<18} {s["members_n"]:>3} {s["zt_d"]:>3} {s["zt_d1"]:>3} {s["zt_d2"]:>3} {s["zt_d3"]:>3} {s["lb2"]:>2} {s["lb3"]:>2} {s["lb4"]:>2} {s["max_lbc"]:>3}  {s["weighted_chg"]:>+5.2f} {s["alpha"]:>+5.2f}  {s["ge5_ratio"]*100:>4.1f}% {s["ge7_ratio"]*100:>4.1f}%  {s["weighted_ratio"]:>4.2f} {s["trend_score"]:>+3} {s["dt_d"]:>3} {s["score"]:>+6.1f}', flush=True)
    
    # 4-30 命中股板块排名
    print(f'\n=== 4-30 命中股 板块排名 ===', flush=True)
    targets = ['688400', '300885', '603711', '603360']
    for code in targets:
        info = market_d.get(code)
        if not info: 
            print(f'  {code}: 不在市场')
            continue
        best_sec, best_score = None, -1e9
        for c in info['concepts']:
            sp = sec_stats.get(c)
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
        
        best_sec, best_score = None, -1e9
        max_lbc = 0; sec_zt_d = 0; sec_alpha = 0; sec_ge7 = 0
        for c in info['concepts']:
            sp = sec_stats.get(c)
            if sp and sp['score'] > best_score:
                best_score = sp['score']
                best_sec = c
                max_lbc = sp['max_lbc']
                sec_zt_d = sp['zt_d']
                sec_alpha = sp['alpha']
                sec_ge7 = sp['ge7_ratio']
        
        if best_sec is None: continue
        candidates.append({
            'code': code, 'name': info['name'],
            'd0_chg': info['chg'], 'volume_ratio': info['ratio'],
            'best_sec': best_sec, 'sec_score': best_score,
            'sec_max_lbc': max_lbc, 'sec_zt_d': sec_zt_d,
            'sec_alpha': sec_alpha, 'sec_ge7_ratio': sec_ge7,
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
    for thr in [20, 30, 40, 50, 60, 70, 80, 90, 100]:
        s = [c for c in valid if c['sec_score'] >= thr]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s)
            print(f'  sec_score≥{thr:>3}: n={len(s):>4}, 涨停 {zt}, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== 复合条件 ===', flush=True)
    for label, cond in [
        ('sec_max_lbc≥3 + 量比≥3', lambda c: c['sec_max_lbc']>=3 and c['volume_ratio']>=3),
        ('sec_max_lbc≥3 + sec_zt_d≥10 + 量比≥2', lambda c: c['sec_max_lbc']>=3 and c['sec_zt_d']>=10 and c['volume_ratio']>=2),
        ('sec_score≥50 + 量比≥3', lambda c: c['sec_score']>=50 and c['volume_ratio']>=3),
        ('sec_score≥60 + 量比≥3', lambda c: c['sec_score']>=60 and c['volume_ratio']>=3),
        ('sec_score≥70 + 量比≥3', lambda c: c['sec_score']>=70 and c['volume_ratio']>=3),
        ('sec_score≥50 + 量比≥2 + d0_chg<5', lambda c: c['sec_score']>=50 and c['volume_ratio']>=2 and c['d0_chg']<5),
        ('sec_score≥60 + 量比≥2 + d0_chg<5', lambda c: c['sec_score']>=60 and c['volume_ratio']>=2 and c['d0_chg']<5),
        ('sec_alpha≥1 + 量比≥3', lambda c: c['sec_alpha']>=1 and c['volume_ratio']>=3),
        ('sec_ge7_ratio≥0.05 + 量比≥3', lambda c: c['sec_ge7_ratio']>=0.05 and c['volume_ratio']>=3),
        ('sec_max_lbc≥2 + sec_alpha≥1 + 量比≥3 + d0_chg<5', lambda c: c['sec_max_lbc']>=2 and c['sec_alpha']>=1 and c['volume_ratio']>=3 and c['d0_chg']<5),
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
    out = WS / 'backtest' / f'sector_strength_v6_{D.replace("-","")}.json'
    sec_data = {sec: dict(s) for sec, s in sec_sorted[:50]}
    with open(out, 'w') as f:
        json.dump({'top_sectors': sec_data, 'candidates': valid, 'market_avg_chg': mkt_avg}, 
                  f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
