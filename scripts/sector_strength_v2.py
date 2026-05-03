#!/usr/bin/env python3
"""板块持续性强度 v2

改进:
1. 正确解析 "首板涨停" / "X天Y板"
2. 排除"宽泛标签"如 融资融券/沪股通/深股通/国企改革/新股与次新股
3. 加 D-1 + D-2 板块涨停数 (累计 2 天热度)
"""
import json, time, urllib.request, math, re
from pathlib import Path
import pywencai
import warnings; warnings.filterwarnings('ignore')
from collections import defaultdict

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')

# 排除宽泛标签 (几乎全市场都有)
EXCLUDE_SECTORS = {
    '融资融券', '沪股通', '深股通', '国企改革', '新股与次新股', 
    '上证A50', '上证180', '沪深300', '中证500', '中证1000',
    'ST板块', 'MSCI中国', '专精特新', '小盘股',  # 这些不是真"题材板块"
    '股权转让(并购重组)',  # 太宽
    '一带一路', '西部大开发',  # 也太宽
}


def safe(v, default=0):
    try:
        f = float(v)
        return default if (math.isnan(f) or math.isinf(f)) else f
    except: return default


def parse_lbc(lbc_str):
    """解析"几天几板": "首板涨停" -> 1, "3天2板" -> 2, "10天8板" -> 8"""
    if not lbc_str: return 0
    if '首' in lbc_str: return 1
    m = re.search(r'(\d+)天(\d+)板', lbc_str)
    if m: return int(m.group(2))
    nums = re.findall(r'(\d+)', lbc_str)
    return int(nums[-1]) if nums else 0


def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689') or code.startswith('8') or code.startswith('92')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


def get_chg(code, target):
    if code.startswith('8') or code.startswith('92'):
        return None
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


def get_zt_sectors(d_str):
    """拉某天涨停板块: sec -> [(code, name, lbc)]"""
    yyyymmdd = d_str.replace('-', '')
    df = pywencai.get(query=f'{d_str} 涨停 所属概念 几天几板', loop=True, timeout=120)
    if df is None or isinstance(df, dict) or len(df) == 0: return {}
    
    sec_zt = defaultdict(list)
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            concepts_str = str(row.get('所属概念', '') or '')
            lbc_str = str(row.get(f'几天几板[{yyyymmdd}]', '') or '')
            lbc = parse_lbc(lbc_str)
            if not code or not concepts_str: continue
            concepts = [c.strip() for c in concepts_str.split(';') if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            for c in concepts:
                sec_zt[c].append({'code': code, 'name': name, 'lbc': lbc})
        except: continue
    return sec_zt


def main():
    print('🔬 板块持续性强度 v2 (4-28+4-29 → 4-30)', flush=True)
    
    # 拉 D-2 (4-28) + D-1 (4-29) 涨停板块
    print('  拉 4-28 涨停板块...', flush=True)
    sec_zt_28 = get_zt_sectors('2026-04-28')
    print(f'    板块数: {len(sec_zt_28)}', flush=True)
    
    print('  拉 4-29 涨停板块...', flush=True)
    sec_zt_29 = get_zt_sectors('2026-04-29')
    print(f'    板块数: {len(sec_zt_29)}', flush=True)
    
    # 板块持续性: 同时在 28 和 29 出现涨停的板块
    persistent_sectors = set(sec_zt_28) & set(sec_zt_29)
    print(f'\n=== 持续性板块 (28+29 都涨停): {len(persistent_sectors)} ===', flush=True)
    sec_persist = []
    for sec in persistent_sectors:
        n28 = len(sec_zt_28[sec])
        n29 = len(sec_zt_29[sec])
        max_lbc_29 = max(m['lbc'] for m in sec_zt_29[sec])
        sec_persist.append({'sec': sec, 'n28': n28, 'n29': n29, 'max_lbc': max_lbc_29, 'total': n28+n29})
    
    sec_persist.sort(key=lambda x: -x['total'])
    print(f'  Top 30 持续性板块 (按 28+29 涨停总数):', flush=True)
    for s in sec_persist[:30]:
        print(f'    {s["sec"]:<25} 28={s["n28"]:>3} 29={s["n29"]:>3} 龙头={s["max_lbc"]}板', flush=True)
    
    # 4-29 全市场候选
    print(f'\n  拉 4-29 全市场...', flush=True)
    df_all = pywencai.get(query='2026-04-29 涨跌幅 量比 收盘价 所属概念', loop=True, timeout=180)
    print(f'  全市场: {len(df_all)} 只', flush=True)
    
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
            if chg < 0 or chg >= 9.5: continue  # 阳柱非涨停
            
            concepts = [c.strip() for c in concepts_str.split(';') 
                       if c.strip() and c.strip() not in EXCLUDE_SECTORS]
            
            # 三个强度指标
            max_n29 = 0          # 此票所属板块中, 4-29 涨停最多的板块涨停数
            max_n28 = 0          # 4-28 同上
            max_persist = 0      # 28+29 持续性板块涨停总数
            max_lead_lbc = 0     # 板块龙头几板
            best_sec = None
            
            for c in concepts:
                n29 = len(sec_zt_29.get(c, []))
                n28 = len(sec_zt_28.get(c, []))
                persist = n28 + n29 if (n28 > 0 and n29 > 0) else 0
                lead_lbc = max((m['lbc'] for m in sec_zt_29.get(c, [])), default=0)
                
                if persist > max_persist:
                    max_persist = persist
                    max_n28 = n28
                    max_n29 = n29
                    max_lead_lbc = lead_lbc
                    best_sec = c
                elif persist == max_persist and n29 > max_n29:
                    max_n29 = n29
                    max_lead_lbc = lead_lbc
                    best_sec = c
            
            candidates.append({
                'code': code, 'name': name,
                'd0_chg': chg, 'volume_ratio': ratio,
                'sec_n28': max_n28, 'sec_n29': max_n29,
                'sec_persist': max_persist, 'sec_lead_lbc': max_lead_lbc,
                'best_sec': best_sec,
            })
        except: continue
    
    print(f'  有效候选 (剔除涨停/ST): {len(candidates)}', flush=True)
    
    # 拉 4-30 涨幅
    sub = [c for c in candidates if c['volume_ratio'] >= 2 and c['sec_persist'] > 0]
    print(f'  量比≥2 + 持续性板块成员: {len(sub)} 只', flush=True)
    
    for i, c in enumerate(sub):
        chg = get_chg(c['code'], '2026-04-30')
        c['chg_4_30'] = chg
        c['is_zt_430'] = is_zt(c['name'], chg, c['code']) if chg is not None else False
        if i % 50 == 0: print(f'    [{i}/{len(sub)}]...', flush=True)
        time.sleep(0.03)
    
    valid = [c for c in sub if c.get('chg_4_30') is not None]
    base = sum(1 for c in valid if c['is_zt_430']) / max(1, len(valid)) * 100
    fm_base = 2.7
    print(f'\n=== 基线 (持续性板块 + 量比≥2): {sum(1 for c in valid if c["is_zt_430"])}/{len(valid)} = {base:.2f}%, lift {base/fm_base:.2f}x ===', flush=True)
    
    print(f'\n=== H1: 板块 4-29 涨停数 ===', flush=True)
    for thr in [3, 5, 8, 10]:
        s = [c for c in valid if c['sec_n29'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  sec_n29≥{thr}: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H2: 板块龙头连板数 ===', flush=True)
    for thr in [2, 3, 4, 5]:
        s = [c for c in valid if c['sec_lead_lbc'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  龙头≥{thr}板: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H3: 持续性 (28+29 总数) ===', flush=True)
    for thr in [5, 10, 15, 20]:
        s = [c for c in valid if c['sec_persist'] >= thr]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  sec_persist≥{thr}: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H4: 复合 ===', flush=True)
    for label, cond in [
        ('龙头≥3板 + 量比≥3', lambda c: c['sec_lead_lbc']>=3 and c['volume_ratio']>=3),
        ('龙头≥2板 + 量比≥3 + d0_chg≥5', lambda c: c['sec_lead_lbc']>=2 and c['volume_ratio']>=3 and c['d0_chg']>=5),
        ('sec_persist≥10 + 量比≥3', lambda c: c['sec_persist']>=10 and c['volume_ratio']>=3),
        ('sec_persist≥10 + 量比≥3 + d0_chg≥5', lambda c: c['sec_persist']>=10 and c['volume_ratio']>=3 and c['d0_chg']>=5),
        ('龙头≥3板 + sec_persist≥5', lambda c: c['sec_lead_lbc']>=3 and c['sec_persist']>=5),
    ]:
        s = [c for c in valid if cond(c)]
        if s:
            r = sum(1 for c in s if c['is_zt_430']) / len(s) * 100
            print(f'  {label}: n={len(s):>4}, 4-30 涨停 {r:.2f}%, lift {r/fm_base:.2f}x', flush=True)
    
    # 4-30 实际涨停的票, 看它们的板块特征
    hits = [c for c in valid if c['is_zt_430']]
    print(f'\n📌 4-30 涨停的 {len(hits)} 只:', flush=True)
    for c in hits:
        print(f'  {c["code"]} {c["name"][:8]:8} 板块={c["best_sec"]:<20} n29={c["sec_n29"]} 龙头={c["sec_lead_lbc"]}板 量比={c["volume_ratio"]:.1f} d0_chg={c["d0_chg"]:.2f}% → +{c["chg_4_30"]:.2f}%', flush=True)
    
    out = WS / 'backtest' / 'sector_strength_v2.json'
    with open(out, 'w') as f:
        json.dump({'persistent_sectors': sec_persist[:50], 'candidates_tested': valid, 'hits': hits}, 
                  f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
