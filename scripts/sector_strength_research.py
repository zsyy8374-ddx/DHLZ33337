#!/usr/bin/env python3
"""板块持续性强度研究

H1: D-1 板块涨停股越多 → 板块成员次日涨停概率↑
H2: D-1 板块龙头连板数越高 → 板块次日涨停概率↑
H3: D-2/D-1 连续 2 天有股涨停的板块 → 板块在主升, lift 高

数据源: 同花顺问财
- D-1 涨停股 + 所属概念 + 连板数 + 涨停原因
- D 全市场涨幅
"""
import json, time, urllib.request, math
from pathlib import Path
import pywencai
import warnings; warnings.filterwarnings('ignore')
from collections import defaultdict

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')


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


def get_chg(code, target):
    prefix = 'sh' if code.startswith('6') else 'sz'
    if code.startswith('8') or code.startswith('92'):
        return None  # 北交所
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
    print('🔬 板块持续性强度研究 (4-29 → 4-30)', flush=True)
    
    # 1. 拉 4-29 涨停股 + 所属概念
    print('  拉 4-29 涨停股...', flush=True)
    df_zt = pywencai.get(query='2026-04-29 涨停 所属概念 连续涨停天数 几天几板', loop=True, timeout=120)
    print(f'  4-29 涨停: {len(df_zt)} 只', flush=True)
    
    # 板块 -> 涨停股列表
    sector_zt = defaultdict(list)
    for _, row in df_zt.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            concepts_str = str(row.get('所属概念', '') or '')
            lbc_str = str(row.get('几天几板[20260429]', '') or '')  # "5天3板"
            chgstreak = safe(row.get('连续涨停天数[20260429]'))
            if not code or not concepts_str: continue
            
            # 解析连板 (如 "3连板", "5天3板", "首板")
            lbc = 1
            if '首' in lbc_str: lbc = 1
            elif '板' in lbc_str:
                # 提取最后一个数字
                import re
                nums = re.findall(r'(\d+)', lbc_str)
                if nums:
                    lbc = int(nums[-1])
            
            concepts = [c.strip() for c in concepts_str.split(';') if c.strip()]
            for c in concepts:
                sector_zt[c].append({
                    'code': code, 'name': name, 'lbc': lbc, 'streak': chgstreak
                })
        except: continue
    
    # 板块强度排名
    print(f'\n=== 4-29 涨停股板块统计 (top 20) ===', flush=True)
    sectors_sorted = sorted(sector_zt.items(), key=lambda x: -len(x[1]))
    for sec, members in sectors_sorted[:20]:
        max_lbc = max(m['lbc'] for m in members)
        print(f'  {sec}: {len(members)} 只涨停, 龙头 {max_lbc} 板', flush=True)
    
    # 2. 拉 4-29 全市场 量比+涨幅 (做候选池)
    print(f'\n  拉 4-29 全市场...', flush=True)
    df_all = pywencai.get(query='2026-04-29 涨跌幅 量比 收盘价 所属概念', loop=True, timeout=180)
    print(f'  全市场: {len(df_all)} 只', flush=True)
    
    # 给每只票算"板块强度"
    candidates = []
    for _, row in df_all.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            if not code or 'ST' in name or '退' in name: continue
            
            chg = safe(row.get('涨跌幅:前复权[20260429]'))
            ratio = safe(row.get('量比[20260429]'))
            close = safe(row.get('收盘价:前复权[20260429]'))
            concepts_str = str(row.get('所属概念', '') or '')
            
            if close < 2 or close > 200: continue
            if chg < 0: continue  # 必须阳线方向
            
            concepts = [c.strip() for c in concepts_str.split(';') if c.strip()]
            
            # 板块强度: 此票所属板块中, 4-29 涨停最多的板块的涨停数 + 龙头板数
            max_sec_zt_count = 0
            max_sec_lead_lbc = 0
            best_sec = None
            for c in concepts:
                if c in sector_zt:
                    n = len(sector_zt[c])
                    if n > max_sec_zt_count:
                        max_sec_zt_count = n
                        max_sec_lead_lbc = max(m['lbc'] for m in sector_zt[c])
                        best_sec = c
            
            candidates.append({
                'code': code, 'name': name,
                'd0_chg': chg, 'volume_ratio': ratio,
                'sec_zt_count': max_sec_zt_count,
                'sec_lead_lbc': max_sec_lead_lbc,
                'best_sec': best_sec,
                'concepts': concepts,
            })
        except: continue
    
    print(f'  有效候选: {len(candidates)}', flush=True)
    
    # 3. 关注高板块强度的候选, 拉 4-30 涨幅看效果
    # 选: 量比>=2 (有热度), 板块涨停数 >= 3 (热门板块)
    sub = [c for c in candidates if c['volume_ratio'] >= 2 and c['sec_zt_count'] >= 3 and c['d0_chg'] < 9.5]
    print(f'\n  量比≥2 + 板块涨停≥3 + 非涨停: {len(sub)} 只', flush=True)
    
    # 拉 4-30 涨幅
    for i, c in enumerate(sub):
        chg = get_chg(c['code'], '2026-04-30')
        c['chg_4_30'] = chg
        c['is_zt_430'] = is_zt(c['name'], chg, c['code']) if chg is not None else False
        if i % 50 == 0: print(f'    [{i}/{len(sub)}]...', flush=True)
        time.sleep(0.03)
    
    valid = [c for c in sub if c.get('chg_4_30') is not None]
    base = sum(1 for c in valid if c['is_zt_430']) / max(1, len(valid)) * 100
    print(f'\n=== 基线 (量比≥2 + 板块涨停≥3 + 非涨停, 4-30 涨停率) ===', flush=True)
    print(f'  {sum(1 for c in valid if c["is_zt_430"])}/{len(valid)} = {base:.2f}%', flush=True)
    
    # 全市场基线 ~2.7%
    fm_base = 2.7
    print(f'  vs 全市场 base 2.7%: lift {base/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H1: 板块涨停数 ===', flush=True)
    for thr in [3, 5, 8, 10, 15]:
        s = [c for c in valid if c['sec_zt_count'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  板块涨停≥{thr}: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift vs FM {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H2: 板块龙头连板数 ===', flush=True)
    for thr in [2, 3, 4, 5]:
        s = [c for c in valid if c['sec_lead_lbc'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  龙头≥{thr}板: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H3: 复合 (板块强 + 量比 + 涨幅) ===', flush=True)
    for label, cond in [
        ('板块涨停≥5 + 量比≥3', lambda c: c['sec_zt_count']>=5 and c['volume_ratio']>=3),
        ('板块涨停≥8 + 量比≥3 + d0_chg≥5', lambda c: c['sec_zt_count']>=8 and c['volume_ratio']>=3 and c['d0_chg']>=5),
        ('龙头≥3板 + 量比≥3', lambda c: c['sec_lead_lbc']>=3 and c['volume_ratio']>=3),
        ('龙头≥3板 + 量比≥3 + d0_chg≥5', lambda c: c['sec_lead_lbc']>=3 and c['volume_ratio']>=3 and c['d0_chg']>=5),
    ]:
        s = [c for c in valid if cond(c)]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  {label}: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift {r/fm_base:.2f}x', flush=True)
    
    # 板块视角: 哪个板块的成员 4-30 涨停最多?
    print(f'\n=== 4-30 各板块次日表现 (Top 10) ===', flush=True)
    sec_perf = defaultdict(lambda: [0, 0])  # sec -> [zt_n, total]
    for c in valid:
        if not c['best_sec']: continue
        sec_perf[c['best_sec']][1] += 1
        if c['is_zt_430']: sec_perf[c['best_sec']][0] += 1
    
    sec_perf_sorted = sorted(sec_perf.items(), key=lambda x: -x[1][0])
    for sec, (zt, total) in sec_perf_sorted[:10]:
        if total >= 3:
            print(f'  {sec}: {zt}/{total} = {zt*100/total:.0f}%', flush=True)
    
    # 落档
    out = WS / 'backtest' / 'sector_strength_4_29.json'
    with open(out, 'w') as f:
        json.dump({'sectors_4_29': {k: v for k, v in sectors_sorted}, 
                   'candidates_tested': valid}, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
