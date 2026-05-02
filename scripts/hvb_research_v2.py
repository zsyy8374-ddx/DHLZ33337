#!/usr/bin/env python3
"""高量柱战法 v2 — 全市场扫描
不用 v18_events, 用全市场 K 线扫所有"高量柱日"
然后看 5 个交易日内是否再涨停
"""
import json, urllib.request, time, sys, os, pickle
from pathlib import Path
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
CKPT = WS / 'backtest' / 'hvb_kline_cache.json'


def is_zt(name, chg, code):
    is_st = 'ST' in (name or '') or '退' in (name or '')
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    if is_st: return chg >= 4.7
    if is_20: return chg >= 19
    return chg >= 9.5


def main():
    print('🔬 高量柱战法 v2: 全市场扫描', flush=True)
    
    # 加载 K 线 cache (我们已经拉过的 ~280 只)
    if not CKPT.exists():
        print('❌ 没 cache, 先跑 hvb_research.py')
        return
    with open(CKPT) as f:
        cache = json.load(f)
    print(f'  K 线 cache: {len(cache)} 只 (从 v1 取)', flush=True)
    
    # 对每只票, 扫描每天 → 看是不是高量柱日 → 看 5 天内是否涨停
    hvb_events = []
    for code, bars in cache.items():
        if len(bars) < 30: continue
        is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
        zt_thr = 19 if is_20 else 9.5
        
        for i in range(20, len(bars) - 5):
            try:
                pre20 = [float(b[5]) for b in bars[i-20:i]]
                d0_vol = float(bars[i][5])
                d0_high = float(bars[i][3])
                d0_low = float(bars[i][4])
                d0_close = float(bars[i][2])
                d0_open = float(bars[i][1])
                d0_prev_close = float(bars[i-1][2])
                d0_chg = (d0_close - d0_prev_close) / d0_prev_close * 100
                
                if d0_vol < max(pre20):  # 不是 20 天高量
                    continue
                
                avg_vol_20 = sum(pre20) / 20
                vol_mult = d0_vol / avg_vol_20 if avg_vol_20 > 0 else 0
                vol_ratio_prev = d0_vol / pre20[-1] if pre20[-1] > 0 else 0
                
                # D+1 ~ D+5 是否涨停 + 是否回踩不破 D0 低点
                future_5 = bars[i+1:i+6]
                if len(future_5) < 5: continue
                
                fut_zt = False
                fut_zt_idx = -1
                for j, b in enumerate(future_5):
                    fut_chg = (float(b[2]) - float(future_5[j-1][2] if j > 0 else bars[i][2])) / float(future_5[j-1][2] if j > 0 else bars[i][2]) * 100
                    if fut_chg >= zt_thr - 0.5:
                        fut_zt = True
                        fut_zt_idx = j
                        break
                
                period_low = min(float(b[4]) for b in future_5)
                held_d0_low = period_low >= d0_low
                
                hvb_events.append({
                    'code': code,
                    'd0_date': bars[i][0],
                    'd0_chg': d0_chg,
                    'd0_vol_mult': vol_mult,
                    'd0_vol_ratio_prev': vol_ratio_prev,
                    'd0_close': d0_close,
                    'd0_low': d0_low,
                    'd0_open': d0_open,
                    'is_yang': d0_close >= d0_open,
                    'fut_zt_5d': fut_zt,
                    'fut_zt_day': fut_zt_idx + 1 if fut_zt else None,
                    'held_d0_low_5d': held_d0_low,
                })
            except Exception:
                continue
    
    print(f'\n📊 全市场高量柱事件: {len(hvb_events)}', flush=True)
    
    # 基线: 高量柱日后 5 天涨停率
    base = sum(1 for e in hvb_events if e['fut_zt_5d']) / max(1, len(hvb_events)) * 100
    print(f'  基线 (高量柱后 5 天涨停): {base:.1f}%', flush=True)
    
    # 子条件
    print(f'\n=== H1: 不同 vol_mult 阈值 ===', flush=True)
    for thr in [1.5, 2, 3, 5, 8]:
        sub = [e for e in hvb_events if e['d0_vol_mult'] >= thr]
        if sub:
            r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
            print(f'  vol_mult ≥ {thr}: n={len(sub):>5}, 5天涨停 {r:.1f}%', flush=True)
    
    print(f'\n=== H2: 高量柱 + D0 阳柱 ===', flush=True)
    sub = [e for e in hvb_events if e['is_yang']]
    if sub:
        r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
        print(f'  is_yang (D0阳柱): n={len(sub)}, 5天涨停 {r:.1f}%', flush=True)
    sub = [e for e in hvb_events if e['is_yang'] and e['d0_chg'] >= 5]
    if sub:
        r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
        print(f'  is_yang + d0_chg≥5: n={len(sub)}, 5天涨停 {r:.1f}%', flush=True)
    sub = [e for e in hvb_events if e['is_yang'] and e['d0_chg'] >= 7]
    if sub:
        r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
        print(f'  is_yang + d0_chg≥7: n={len(sub)}, 5天涨停 {r:.1f}%', flush=True)
    
    print(f'\n=== H3: 高量柱 + 高量不破 ===', flush=True)
    sub = [e for e in hvb_events if e['held_d0_low_5d']]
    if sub:
        r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
        print(f'  held_d0_low: n={len(sub)}, 5天涨停 {r:.1f}%', flush=True)
    sub = [e for e in hvb_events if e['held_d0_low_5d'] and e['is_yang'] and e['d0_chg'] >= 5]
    if sub:
        r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
        print(f'  held + 阳柱 + d0_chg≥5: n={len(sub)}, 5天涨停 {r:.1f}%', flush=True)
    
    print(f'\n=== H4: 高量柱 + D0 涨停 (经典爆量首板) ===', flush=True)
    sub = [e for e in hvb_events if e['d0_chg'] >= 9.5]  # 涨停
    if sub:
        r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
        print(f'  d0_chg≥9.5 (主板涨停): n={len(sub)}, 5天再涨停 {r:.1f}%', flush=True)
    
    print(f'\n=== H5: 复合最强 ===', flush=True)
    for label, cond in [
        ('vol_mult≥3 + d0_chg≥9.5 + held', 
         lambda e: e['d0_vol_mult']>=3 and e['d0_chg']>=9.5 and e['held_d0_low_5d']),
        ('vol_mult≥2 + d0_chg≥7 + 阳柱 + held', 
         lambda e: e['d0_vol_mult']>=2 and e['d0_chg']>=7 and e['is_yang'] and e['held_d0_low_5d']),
        ('vol_mult≥3 + d0_chg≥7 + 阳柱', 
         lambda e: e['d0_vol_mult']>=3 and e['d0_chg']>=7 and e['is_yang']),
    ]:
        sub = [e for e in hvb_events if cond(e)]
        if sub:
            r = sum(1 for e in sub if e['fut_zt_5d']) / len(sub) * 100
            print(f'  {label}: n={len(sub)}, 5天涨停 {r:.1f}%', flush=True)
    
    # 落档
    out = WS / 'backtest' / 'hvb_research_v2_results.json'
    with open(out, 'w') as f:
        json.dump({
            'base_rate': base,
            'n_events': len(hvb_events),
            'sample_codes_used': len(cache),
            'events': hvb_events[:1000]
        }, f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
