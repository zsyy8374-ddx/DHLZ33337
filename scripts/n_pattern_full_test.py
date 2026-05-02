#!/usr/bin/env python3
"""N 字回踩 — 全市场 4-29 D0 → 4-30 验证

D0 = 2026-04-29
信号: 当天站回 MA10 + 量比≥1.1 + 阳柱
回看: D-3 到 D-10 找回调段 + P1
"""
import json, urllib.request, time, pywencai
import warnings; warnings.filterwarnings('ignore')
from pathlib import Path

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')


def safe(v):
    import math
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


def get_kline(code, days=30):
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,{days},qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        return d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
    except: return []


def find_n_at(bars, d0_idx, code):
    """检查 d0 是否符合 N 字"""
    if d0_idx < 15: return None
    try:
        d0_close = float(bars[d0_idx][2])
        d0_open = float(bars[d0_idx][1])
        d0_vol = float(bars[d0_idx][5])
        d0_prev_close = float(bars[d0_idx-1][2])
        d0_prev_vol = float(bars[d0_idx-1][5])
        d0_chg = (d0_close - d0_prev_close) / d0_prev_close * 100
        
        # 阳柱 + 放量
        if d0_close < d0_open: return None
        if d0_vol < d0_prev_vol * 1.1: return None
        
        # MA10
        closes = [float(bars[i][2]) for i in range(d0_idx-9, d0_idx+1)]
        ma10_d0 = sum(closes) / 10
        if d0_close < ma10_d0: return None  # 必须站上 MA10
        
        prev_closes = [float(bars[i][2]) for i in range(d0_idx-10, d0_idx)]
        ma10_prev = sum(prev_closes) / 10
        if float(bars[d0_idx-1][2]) >= ma10_prev: return None  # 前一日还在 MA10 下
        
        # 找 N 字结构
        for k in range(3, 11):
            if d0_idx - k < 5: break
            p1_window_start = max(0, d0_idx - k - 5)
            p1_window_end = d0_idx - k
            p1_highs = [float(bars[i][3]) for i in range(p1_window_start, p1_window_end+1)]
            p1_high = max(p1_highs)
            p1_high_idx = p1_window_start + p1_highs.index(p1_high)
            
            p0_window_start = max(0, p1_high_idx - 10)
            p0_lows = [float(bars[i][4]) for i in range(p0_window_start, p1_high_idx+1)]
            p0_low = min(p0_lows)
            
            p1_gain = (p1_high - p0_low) / p0_low * 100
            if p1_gain < 10: continue
            
            p2_lows = [float(bars[i][4]) for i in range(p1_high_idx+1, d0_idx+1)]
            if not p2_lows: continue
            p2_low = min(p2_lows)
            p2_drop = (p1_high - p2_low) / p1_high * 100
            
            if p2_drop < 3 or p2_drop > 20: continue
            if p2_low <= p0_low: continue
            
            return {
                'code': code,
                'd0_chg': d0_chg,
                'd0_vol_ratio': d0_vol / d0_prev_vol,
                'p1_gain': p1_gain,
                'p2_drop': p2_drop,
                'k_days': k,
                'p1_high': p1_high,
                'p2_low': p2_low,
                'd0_close': d0_close,
            }
    except: pass
    return None


def main():
    print('🔬 N 字回踩 — 全市场 4-29 D0 → 4-30 验证', flush=True)
    
    # 拉 4-29 全市场
    df = pywencai.get(query='2026-04-29 涨跌幅 收盘价 开盘价 成交量 量比 5日均量 MA10', 
                      loop=True, timeout=180)
    print(f'  全市场 {len(df)} 行', flush=True)
    
    # 第一步过滤: 量比 >= 1.1, d0 涨幅 >= 0
    candidates = []
    for _, row in df.iterrows():
        try:
            code = str(row.get('code', '')).strip()
            name = str(row.get('股票简称', '')).strip()
            if not code or 'ST' in name or '退' in name: continue
            
            ratio = safe(row.get('量比[20260429]'))
            d0_chg = safe(row.get('涨跌幅:前复权[20260429]'))
            d0_close = safe(row.get('收盘价:前复权[20260429]'))
            
            if not all([ratio, d0_chg is not None, d0_close]): continue
            if d0_close < 2 or d0_close > 200: continue
            if ratio < 1.1: continue
            if d0_chg < 0: continue  # 必须是阳线方向
            if d0_chg >= 9.5: continue  # 涨停不算 N 字 (是首板)
            
            candidates.append({'code': code, 'name': name, 'd0_chg': d0_chg, 'volume_ratio': ratio})
        except: continue
    
    print(f'  量比≥1.1 + d0_chg [0~9.5%]: {len(candidates)}', flush=True)
    
    # 第二步: 拉 K 线找 N 字结构
    n_patterns = []
    target_d0 = '2026-04-29'
    for i, c in enumerate(candidates):
        if i % 50 == 0:
            print(f'    [{i}/{len(candidates)}] N 字: {len(n_patterns)}', flush=True)
        bars = get_kline(c['code'], days=40)
        if not bars: continue
        d0_idx = next((j for j, b in enumerate(bars) if b[0] == target_d0), -1)
        if d0_idx < 0: continue
        p = find_n_at(bars, d0_idx, c['code'])
        if p:
            p['name'] = c['name']
            p['volume_ratio'] = c['volume_ratio']
            
            # 拉 4-30 涨幅
            if d0_idx + 1 < len(bars):
                d1 = bars[d0_idx + 1]
                if d1[0] == '2026-04-30':
                    d1_close = float(d1[2])
                    d1_chg = (d1_close - p['d0_close']) / p['d0_close'] * 100
                    p['chg_4_30'] = d1_chg
                    p['is_zt_430'] = is_zt(c['name'], d1_chg, c['code'])
            
            n_patterns.append(p)
        time.sleep(0.02)
    
    print(f'\n  N 字形态: {len(n_patterns)}', flush=True)
    
    # 验证
    valid = [p for p in n_patterns if 'chg_4_30' in p]
    print(f'  有 4-30 数据: {len(valid)}', flush=True)
    
    if not valid: 
        print('❌ 没有验证数据')
        return
    
    base = sum(1 for p in valid if p.get('is_zt_430')) / len(valid) * 100
    avg = sum(p['chg_4_30'] for p in valid) / len(valid)
    print(f'\n=== 全市场基线 ===', flush=True)
    print(f'  4-30 涨停率: {base:.2f}% ({sum(1 for p in valid if p.get("is_zt_430"))}/{len(valid)})', flush=True)
    print(f'  4-30 平均涨幅: {avg:+.2f}%', flush=True)
    
    # 全市场比较 (用我们之前 hvb_full_market 的 base = 2.69%)
    fm_base = 2.69  # 全市场量比≥2 池
    print(f'\n  vs 量比≥2 全市场基线 2.69%, lift {base/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H1: P1 涨幅 ===', flush=True)
    for thr in [10, 15, 20, 30]:
        sub = [p for p in valid if p['p1_gain'] >= thr]
        if sub:
            r = sum(1 for p in sub if p.get('is_zt_430')) / len(sub) * 100
            print(f'  P1≥{thr}%: n={len(sub):>4}, 4-30 涨停 {r:.2f}%, lift vs FM {r/fm_base:.2f}x', flush=True)
    
    print(f'\n=== H2: 回调幅度 ===', flush=True)
    for label, lo, hi in [('小调 3-7%', 3, 7), ('中调 7-12%', 7, 12), ('深调 12-20%', 12, 20)]:
        sub = [p for p in valid if lo <= p['p2_drop'] < hi]
        if sub:
            r = sum(1 for p in sub if p.get('is_zt_430')) / len(sub) * 100
            print(f'  {label}: n={len(sub):>4}, 4-30 涨停 {r:.2f}%', flush=True)
    
    print(f'\n=== H3: 复合 ===', flush=True)
    for label, cond in [
        ('P1≥15 + 深调 12-20', lambda p: p['p1_gain']>=15 and p['p2_drop']>=12),
        ('P1≥20 + 阳量', lambda p: p['p1_gain']>=20 and p['volume_ratio']>=1.5),
        ('P1≥30 (强势)', lambda p: p['p1_gain']>=30),
    ]:
        sub = [p for p in valid if cond(p)]
        if sub:
            r = sum(1 for p in sub if p.get('is_zt_430')) / len(sub) * 100
            print(f'  {label}: n={len(sub):>4}, 4-30 涨停 {r:.2f}%', flush=True)
    
    # 看具体涨停的票
    hits = [p for p in valid if p.get('is_zt_430')]
    print(f'\n📌 4-30 涨停的 N 字股 ({len(hits)} 只):', flush=True)
    for p in hits[:15]:
        print(f'  {p["code"]} {p["name"][:8]:8} P1={p["p1_gain"]:.0f}% 回调={p["p2_drop"]:.0f}% k={p["k_days"]}d D0_chg={p["d0_chg"]:.2f}% 量比={p["volume_ratio"]:.1f} → {p["chg_4_30"]:+.2f}% 🚀', flush=True)
    
    out = WS / 'backtest' / 'n_pattern_4_29_full.json'
    with open(out, 'w') as f:
        json.dump({'base_rate_pool': base, 'patterns': valid}, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
