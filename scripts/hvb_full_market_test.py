#!/usr/bin/env python3
"""高量柱战法 — 全市场单日测试
用 pywencai 拉 4-29 全市场, 找出"高量柱"票, 看 4-30 涨幅
"""
import json, pywencai, urllib.request, time
import warnings; warnings.filterwarnings('ignore')
import math
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')


def safe(v):
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except: return None


def is_zt(name, chg, code):
    if chg is None: return False
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


def get_chg(code, target='2026-04-30'):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,5,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        for i, b in enumerate(bars):
            if b[0] == target and i > 0:
                today, prev = float(b[2]), float(bars[i-1][2])
                return (today - prev) / prev * 100
    except: pass
    return None


def main():
    print('🔬 高量柱 — 全市场 4-29 → 4-30 测试', flush=True)
    
    df = pywencai.get(query='2026-04-29 量比 涨跌幅 成交量 收盘价 最高价 最低价 5日均量 振幅 成交额 换手率 开盘价', 
                      loop=True, timeout=180)
    print(f'  4-29 全市场: {len(df)} 只', flush=True)
    
    # 提取高量柱条件
    candidates = []
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            if not code or 'ST' in name or '退' in name: continue
            
            ratio = safe(row.get('量比[20260429]'))
            d0_chg = safe(row.get('涨跌幅:前复权[20260429]'))
            d0_vol = safe(row.get('成交量[20260429]'))
            d0_5d_avg = safe(row.get('5日vol[20260429]'))
            d0_close = safe(row.get('收盘价:前复权[20260429]'))
            d0_high = safe(row.get('最高价:前复权[20260429]'))
            d0_low = safe(row.get('最低价:前复权[20260429]'))
            d0_open = safe(row.get('开盘价:前复权[20260429]'))
            
            if not all([ratio, d0_chg, d0_close, d0_open]): continue
            if d0_close < 2 or d0_close > 200: continue  # 滤掉低价/高价
            
            vol_mult = d0_vol / d0_5d_avg if d0_5d_avg and d0_5d_avg > 0 else 0
            is_yang = d0_close >= d0_open
            
            candidates.append({
                'code': code,
                'name': name,
                'd0_chg': d0_chg,
                'volume_ratio': ratio,
                'vol_mult': vol_mult,
                'd0_close': d0_close,
                'd0_high': d0_high,
                'd0_low': d0_low,
                'is_yang': is_yang,
                'turn': safe(row.get('换手率[20260429]')) or 0,
                'amplitude': safe(row.get('振幅[20260429]')) or 0,
            })
        except Exception:
            continue
    
    print(f'  有效候选: {len(candidates)}', flush=True)
    
    # 全市场基线 (4-29 → 4-30 涨停率)
    print(f'\n=== 拉 4-30 实际涨幅 ===', flush=True)
    print(f'  全市场太大 ({len(candidates)}), 只拉量比 ≥ 2 的', flush=True)
    
    sub_for_test = [c for c in candidates if c['volume_ratio'] >= 2]
    print(f'  量比 ≥ 2: {len(sub_for_test)} 只 拉 K', flush=True)
    
    for i, c in enumerate(sub_for_test):
        chg = get_chg(c['code'])
        c['chg_4_30'] = chg
        c['is_zt_430'] = is_zt(c['name'], chg, c['code'])
        if i % 50 == 0:
            print(f'    {i}/{len(sub_for_test)}...', flush=True)
        time.sleep(0.03)
    
    # 测试条件
    valid = [c for c in sub_for_test if c.get('chg_4_30') is not None]
    base = sum(1 for c in valid if c['is_zt_430']) / max(1, len(valid)) * 100
    print(f'\n📊 基线 (量比≥2 池里 4-30 涨停率): {base:.2f}% ({sum(1 for c in valid if c["is_zt_430"])}/{len(valid)})', flush=True)
    
    print(f'\n=== H1: 不同条件 ===', flush=True)
    for label, cond in [
        ('量比≥2', lambda c: c['volume_ratio']>=2),
        ('量比≥3', lambda c: c['volume_ratio']>=3),
        ('量比≥5', lambda c: c['volume_ratio']>=5),
        ('量比≥10', lambda c: c['volume_ratio']>=10),
        ('量比≥3 + d0_chg≥7', lambda c: c['volume_ratio']>=3 and c['d0_chg']>=7),
        ('量比≥3 + d0_chg≥7 + 阳柱', lambda c: c['volume_ratio']>=3 and c['d0_chg']>=7 and c['is_yang']),
        ('量比≥3 + 涨停 (≥9.5)', lambda c: c['volume_ratio']>=3 and c['d0_chg']>=9.5),
        ('量比≥5 + d0_chg≥7', lambda c: c['volume_ratio']>=5 and c['d0_chg']>=7),
        ('量比≥3 + 阳柱 + 换手≥3%', lambda c: c['volume_ratio']>=3 and c['is_yang'] and c['turn']>=3),
        ('量比≥3 + 振幅≥7', lambda c: c['volume_ratio']>=3 and c['amplitude']>=7),
    ]:
        sub = [c for c in valid if cond(c)]
        if sub:
            r = sum(1 for c in sub if c['is_zt_430']) / len(sub) * 100
            lift = r / base if base > 0 else 0
            print(f'  {label}: n={len(sub):>4}, 4-30 涨停 {r:.2f}% (lift {lift:.2f}x)', flush=True)
    
    # Top N: 按量比排序看 Top 命中
    print(f'\n=== H2: 按量比 + d0_chg 综合排序 ===', flush=True)
    valid.sort(key=lambda x: -(x['volume_ratio']*0.5 + x['d0_chg']*0.5))
    for k in [10, 20, 30, 50, 100]:
        if len(valid) < k: continue
        sub = valid[:k]
        zt = sum(1 for c in sub if c['is_zt_430'])
        print(f'  Top {k}: 涨停 {zt}/{k} ({zt*100/k:.0f}%)', flush=True)
    
    # 看具体 Top 10
    print(f'\n📌 Top 10 (按 0.5*量比 + 0.5*涨幅):', flush=True)
    for i, c in enumerate(valid[:10], 1):
        zt_s = '✅' if c['is_zt_430'] else '❌'
        chg_s = f'{c.get("chg_4_30",0):+.2f}%' if c.get('chg_4_30') is not None else 'NA'
        print(f'  {i:>2}. {c["code"]} {c["name"][:8]:8} 量比={c["volume_ratio"]:>5.1f} d0_chg={c["d0_chg"]:>6.2f}% → 4-30 {chg_s} {zt_s}', flush=True)
    
    out = WS / 'backtest' / 'hvb_full_market_4_29.json'
    with open(out, 'w') as f:
        json.dump({'base_rate': base, 'tested': valid}, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
