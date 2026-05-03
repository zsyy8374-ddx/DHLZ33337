#!/usr/bin/env python3
"""板块持续性 v4 — 真正的"持续性"模型

核心问题: 一个板块**会不会持续走强**?

5 个真正的持续性维度:

1. **热度趋势** (3 天斜率)
   - zt_count_d (D 涨停数), zt_count_d-1, zt_count_d-2
   - trend_score: 递增 +1, 加速 +2, 衰减 -1, 退潮 -2

2. **赚钱效应** (D 日板块成员表现)
   - up_ratio: 板块涨幅>0 占比
   - avg_chg: 板块成员平均涨幅
   - top10_avg_chg: 前 10 强成员平均涨幅 (排除尾部)

3. **资金活跃度**
   - vol_ratio: 板块今日总成交额 / 5 日均
   - 量比 ≥ 1.5 = 资金涌入

4. **质量分** (D 涨停股质量)
   - first_zt_time_avg: 平均首次涨停时间 (越早越强)
   - 早盘涨停 (<10:30) 比例

5. **退潮反向**
   - dt_count: 板块跌停数 (越多越退潮)
   - 昨日涨停今日跌停 = 强烈退潮

综合分:
持续性分 = 热度趋势 × 5 + 赚钱效应 × 3 + 资金活跃 × 2 + 质量 × 2 - 退潮 × 4
"""
import json, time, urllib.request, math, re
from pathlib import Path
import pywencai
import warnings; warnings.filterwarnings('ignore')
from collections import defaultdict
from datetime import datetime, timedelta

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


def get_market_data(d_str):
    """拉某天全市场: code -> {name, chg, ratio, close, concepts, first_zt_time}"""
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
            
            data[code] = {
                'name': name, 'chg': chg, 'ratio': ratio, 'close': close,
                'amount': amount, 'concepts': concepts,
                'is_zt': is_zt(name, chg, code),
                'is_dt': chg <= -9.5 if not ('ST' in name or '退' in name) else chg <= -4.7,
            }
        except: continue
    return data


def get_zt_with_time(d_str, want_time=False):
    """拉某天涨停 + 概念 (+ 首次涨停时间, 但 want_time=False 时不查 time, 因为 wencai 历史日期查 time 字段会丢数据)"""
    yyyymmdd = d_str.replace('-', '')
    q = f'{d_str} 涨停 所属概念 首次涨停时间' if want_time else f'{d_str} 涨停 所属概念'
    df = pywencai.get(query=q, loop=True, timeout=120)
    if df is None or isinstance(df, dict): return {}
    
    data = {}
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            time_raw = str(row.get(f'首次涨停时间[{yyyymmdd}]', '') or '').strip()
            concepts_str = str(row.get('所属概念', '') or '')
            if not code: continue
            
            # 解析时间: " 09:31:23"  -> 09:31
            time_min = 240  # 默认 14:30 = 240 min from 09:30
            m = re.match(r'\s*(\d{2}):(\d{2})', time_raw)
            if m:
                hh, mm = int(m.group(1)), int(m.group(2))
                if hh < 12:
                    time_min = (hh - 9) * 60 + (mm - 30) if hh >= 9 else 0
                else:
                    time_min = (hh - 9) * 60 + (mm - 30) - 90  # 减午休
            
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            data[code] = {'name': name, 'concepts': concepts, 'first_zt_time_min': time_min}
        except: continue
    return data


def get_dt_set(d_str):
    df = pywencai.get(query=f'{d_str} 跌停', loop=True, timeout=120)
    if df is None or isinstance(df, dict): return set()
    return set(str(row.get('code', '')).strip() for _, row in df.iterrows() if row.get('code'))


def compute_sector_persistence(d, d_prev, d_prev2, d_prev3):
    """计算板块持续性 5 维"""
    print(f'  [1/6] 拉 {d_prev3} 涨停...', flush=True)
    zt_d3 = get_zt_with_time(d_prev3, want_time=False)
    print(f'    {len(zt_d3)} 只', flush=True)
    
    print(f'  [2/6] 拉 {d_prev2} 涨停...', flush=True)
    zt_d2 = get_zt_with_time(d_prev2, want_time=False)
    print(f'    {len(zt_d2)} 只', flush=True)
    
    print(f'  [3/6] 拉 {d_prev} 涨停...', flush=True)
    zt_d1 = get_zt_with_time(d_prev, want_time=False)
    print(f'    {len(zt_d1)} 只', flush=True)
    
    print(f'  [4/6] 拉 {d} 涨停 + 全市场...', flush=True)
    # 不加 want_time 避免 wencai 返回少 (仅 28 只), 上下文却能拉到 119 只
    zt_d = get_zt_with_time(d, want_time=False)
    print(f'    涨停 {len(zt_d)} 只', flush=True)
    
    market_d = get_market_data(d)
    print(f'    全市场 {len(market_d)} 只', flush=True)
    
    print(f'  [5/6] 拉 {d} 跌停...', flush=True)
    dt_d = get_dt_set(d)
    print(f'    {len(dt_d)} 只', flush=True)
    
    print(f'  [6/6] 计算板块持续性...', flush=True)
    
    # 板块成员 = D 全市场所有票按概念分类
    sector_members = defaultdict(list)  # sec -> [code, ...]
    for code, info in market_d.items():
        for c in info['concepts']:
            sector_members[c].append(code)
    
    # 板块涨停 (按日)
    sec_zt_d3 = defaultdict(list)
    sec_zt_d2 = defaultdict(list)
    sec_zt_d1 = defaultdict(list)
    sec_zt_d = defaultdict(list)
    for zt_dict, sec_dict in [(zt_d3, sec_zt_d3), (zt_d2, sec_zt_d2), (zt_d1, sec_zt_d1), (zt_d, sec_zt_d)]:
        for code, info in zt_dict.items():
            for c in info['concepts']:
                sec_dict[c].append({'code': code, 'name': info['name'], 'time_min': info['first_zt_time_min']})
    
    # 计算每个板块的 5 维持续性
    sector_persistence = {}
    for sec in set(sector_members) | set(sec_zt_d):
        members = sector_members.get(sec, [])
        zt_d_list = sec_zt_d.get(sec, [])
        zt_d1_n = len(sec_zt_d1.get(sec, []))
        zt_d2_n = len(sec_zt_d2.get(sec, []))
        zt_d3_n = len(sec_zt_d3.get(sec, []))
        
        if not members or len(members) < 5: continue
        
        # === 1. 热度趋势 (3 天斜率) ===
        # 用线性回归斜率
        zt_seq = [zt_d3_n, zt_d2_n, zt_d1_n, len(zt_d_list)]
        # 简单斜率 (D - D-3) / 3 (反映 4 天热度变化)
        trend_raw = (zt_seq[3] - zt_seq[0])
        trend_score = 0
        if zt_seq[3] >= 5:  # 至少 5 个涨停才看趋势
            if trend_raw > 5: trend_score = 2  # 加速
            elif trend_raw > 0: trend_score = 1  # 递增
            elif trend_raw == 0: trend_score = 0
            elif trend_raw > -5: trend_score = -1  # 衰减
            else: trend_score = -2  # 退潮
        
        # === 2. 赚钱效应 (D 日表现) ===
        member_chgs = [market_d[c]['chg'] for c in members if c in market_d and market_d[c]['chg'] is not None]
        if member_chgs:
            up_ratio = sum(1 for x in member_chgs if x > 0) / len(member_chgs)
            avg_chg = sum(member_chgs) / len(member_chgs)
            top10 = sorted(member_chgs, reverse=True)[:10]
            top10_avg = sum(top10) / len(top10) if top10 else 0
        else:
            up_ratio = 0; avg_chg = 0; top10_avg = 0
        
        # 赚钱效应分: avg_chg >= 2% + up_ratio >= 0.5 = 强
        money_score = 0
        if avg_chg >= 3 and up_ratio >= 0.6: money_score = 2
        elif avg_chg >= 1 and up_ratio >= 0.5: money_score = 1
        elif avg_chg >= 0: money_score = 0
        elif avg_chg >= -2: money_score = -1
        else: money_score = -2
        
        # === 3. 资金活跃度 ===
        # 板块今日总成交额 / 板块成员数
        total_amount = sum(market_d[c]['amount'] for c in members 
                          if c in market_d and market_d[c]['amount'])
        avg_ratio = sum(market_d[c]['ratio'] for c in members 
                       if c in market_d and market_d[c]['ratio']) / max(1, len([c for c in members if c in market_d and market_d[c]['ratio']]))
        
        money_flow_score = 0
        if avg_ratio >= 1.8: money_flow_score = 2
        elif avg_ratio >= 1.3: money_flow_score = 1
        elif avg_ratio >= 1: money_flow_score = 0
        else: money_flow_score = -1
        
        # === 4. 质量分 (暂不用早盘涨停, 后续从另外查询拉) ===
        # TODO: 可加多连板占比作为质量分
        quality_score = 0
        early_ratio = 0
        
        # === 5. 退潮反向 ===
        dt_count = sum(1 for c in members if c in dt_d)
        dt_score = 0
        if dt_count >= 3: dt_score = -2
        elif dt_count >= 1: dt_score = -1
        
        # 昨日涨停今日跌停 (强烈退潮)
        zt_d1_codes = set(z['code'] for z in sec_zt_d1.get(sec, []))
        flip_dt = len(zt_d1_codes & dt_d)
        if flip_dt >= 1: dt_score -= 2
        
        # === 综合 ===
        persistence = (
            trend_score * 5 +
            money_score * 3 +
            money_flow_score * 2 +
            quality_score * 2 +
            dt_score * 4
        )
        
        sector_persistence[sec] = {
            'sec': sec,
            'members_n': len(members),
            'zt_d': len(zt_d_list),
            'zt_d1': zt_d1_n, 'zt_d2': zt_d2_n, 'zt_d3': zt_d3_n,
            'zt_seq': zt_seq,
            'trend_raw': trend_raw, 'trend_score': trend_score,
            'up_ratio': up_ratio, 'avg_chg': avg_chg, 'top10_avg': top10_avg,
            'money_score': money_score,
            'avg_ratio': avg_ratio, 'money_flow_score': money_flow_score,
            'early_zt_ratio': early_ratio, 'quality_score': quality_score,
            'dt_count': dt_count, 'flip_dt': flip_dt, 'dt_score': dt_score,
            'persistence': persistence,
        }
    
    return sector_persistence, market_d, zt_d


def get_chg_next(code, target_day):
    if code.startswith('8') or code.startswith('92'): return None
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        for i, b in enumerate(bars):
            if b[0] == target_day and i > 0:
                return (float(b[2]) - float(bars[i-1][2])) / float(bars[i-1][2]) * 100
    except: pass
    return None


def main():
    D = '2026-04-29'
    D1 = '2026-04-28'
    D2 = '2026-04-24'  # 4-25 周六
    D3 = '2026-04-23'
    D_NEXT = '2026-04-30'
    
    print(f'🔬 板块持续性 v4 ({D}: 5 维深度模型)\n', flush=True)
    
    sec_persist, market_d, zt_d = compute_sector_persistence(D, D1, D2, D3)
    
    # Top 板块 (按 persistence)
    sec_sorted = sorted(sec_persist.items(), key=lambda x: -x[1]['persistence'])
    print(f'\n=== Top 20 持续性板块 ({len(sec_persist)} 总数) ===', flush=True)
    print(f'  {"板块":<22} 成员 涨停D {"D-1":>3} {"D-2":>3} {"D-3":>3} 趋势 平均%涨 量比 早涨% 跌停 持续分', flush=True)
    for sec, s in sec_sorted[:20]:
        print(f'  {sec:<22} {s["members_n"]:>3} {s["zt_d"]:>3}  {s["zt_d1"]:>3} {s["zt_d2"]:>3} {s["zt_d3"]:>3} {s["trend_score"]:>+2}  {s["avg_chg"]:>+5.2f} {s["avg_ratio"]:>4.2f} {s["early_zt_ratio"]:>5.0%} {s["dt_count"]:>3}  {s["persistence"]:>+5.1f}', flush=True)
    
    # 看一下 4-30 涨停的 4 只在持续性 top 板块的位置
    print(f'\n=== 4-30 命中股的板块 持续性排名 ===', flush=True)
    targets = ['688400', '300885', '603711', '603360']
    for code in targets:
        if code not in market_d: 
            print(f'  {code}: 不在 D 全市场 (可能涨停)')
            continue
        info = market_d[code]
        # 找此票最强板块
        best_sec = None
        best_persist = -100
        for c in info['concepts']:
            if c in sec_persist and sec_persist[c]['persistence'] > best_persist:
                best_persist = sec_persist[c]['persistence']
                best_sec = c
        if best_sec:
            rank = next((i for i, (s, _) in enumerate(sec_sorted) if s == best_sec), -1) + 1
            print(f'  {code} {info["name"]}: 板块={best_sec} 持续分={best_persist:.1f} (排名 {rank})')
    
    # 候选股: 在持续分 top N 板块 + 量比 + 温和上涨
    print(f'\n=== 候选股测试 ===', flush=True)
    
    # 阈值: 持续分 ≥ X
    candidates_all = []
    for code, info in market_d.items():
        if info['is_zt']: continue  # D 涨停跳过
        if info['chg'] < 0: continue  # 阴柱跳过
        if info['close'] < 2 or info['close'] > 200: continue
        if 'ST' in info['name'] or '退' in info['name']: continue
        
        best_persist = -100
        best_sec = None
        for c in info['concepts']:
            sp = sec_persist.get(c)
            if sp and sp['persistence'] > best_persist:
                best_persist = sp['persistence']
                best_sec = c
        
        if best_sec is None: continue
        candidates_all.append({
            'code': code, 'name': info['name'],
            'd0_chg': info['chg'], 'volume_ratio': info['ratio'],
            'best_sec': best_sec, 'persistence': best_persist,
        })
    
    print(f'  全部候选 (非涨停 + 阳柱 + 在板块): {len(candidates_all)}', flush=True)
    
    # 按持续分 + 量比阈值筛选, 拉 D+1 涨幅
    sub = [c for c in candidates_all if c['volume_ratio'] >= 2 and c['persistence'] >= 5]
    print(f'  量比≥2 + 持续分≥5: {len(sub)} 只, 拉 {D_NEXT}...', flush=True)
    
    for i, c in enumerate(sub):
        chg = get_chg_next(c['code'], D_NEXT)
        c['chg_next'] = chg
        c['is_zt_next'] = is_zt(c['name'], chg, c['code']) if chg is not None else False
        if i % 50 == 0 and i: print(f'    [{i}/{len(sub)}]...', flush=True)
        time.sleep(0.03)
    
    valid = [c for c in sub if c.get('chg_next') is not None]
    print(f'\n=== 阈值测试 (vs FM 2.7%) ===', flush=True)
    fm_base = 2.7
    for thr in [0, 5, 10, 15, 20, 30]:
        s = [c for c in valid if c['persistence'] >= thr]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s)
            print(f'  持续分≥{thr:>3}: n={len(s):>4}, 涨停 {zt}, lift {r/fm_base:.2f}x', flush=True)
    
    # 复合条件
    print(f'\n=== 复合条件 ===', flush=True)
    for label, cond in [
        ('持续分≥10 + 量比≥3', lambda c: c['persistence']>=10 and c['volume_ratio']>=3),
        ('持续分≥10 + 量比≥3 + d0_chg<5', lambda c: c['persistence']>=10 and c['volume_ratio']>=3 and c['d0_chg']<5),
        ('持续分≥15 + 量比≥3', lambda c: c['persistence']>=15 and c['volume_ratio']>=3),
        ('持续分≥20 + 量比≥3', lambda c: c['persistence']>=20 and c['volume_ratio']>=3),
        ('持续分≥10 + 量比≥2 + d0_chg<5', lambda c: c['persistence']>=10 and c['volume_ratio']>=2 and c['d0_chg']<5),
    ]:
        s = [c for c in valid if cond(c)]
        if s:
            zt = sum(1 for c in s if c['is_zt_next'])
            r = zt*100/len(s) if s else 0
            print(f'  {label}: n={len(s):>3}, 涨停 {zt}, lift {r/fm_base:.2f}x', flush=True)
            for c in s:
                if c['is_zt_next']:
                    print(f'      🚀 {c["code"]} {c["name"]} 板块={c["best_sec"]} 持续分={c["persistence"]:.1f}', flush=True)
    
    # 落档
    out = WS / 'backtest' / f'sector_persistence_v4_{D.replace("-","")}.json'
    sec_data_save = {sec: dict(s) for sec, s in sec_sorted[:50]}
    with open(out, 'w') as f:
        json.dump({'top_sectors': sec_data_save, 'candidates': valid}, 
                  f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
