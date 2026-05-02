#!/usr/bin/env python3
"""高量柱战法研究 — 全量回测
高量柱 (HVB) 定义:
  vol[D0] = MAX(vol[D0-N : D0])  N=20
  vol[D0] >= 1.5 × vol[D0-1]  (强高量柱)

测试假设:
H1: D0 是高量柱 → reversal 概率提升
H2: 高量柱 + "回调不破 D0 低点" → 强 reversal 信号 ⭐
H3: 高量柱 + 大涨幅 D0 (≥7%) → 启动概率提升

落档:
  backtest/hvb_research_results.json
"""
import json, urllib.request, time, sys, os, pickle
from pathlib import Path
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
CKPT = WS / 'backtest' / 'hvb_kline_cache.json'


def get_kline(code, days=60, cache=None):
    if cache is not None and code in cache:
        return cache[code]
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,{days},qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        if cache is not None:
            cache[code] = bars
        return bars
    except Exception:
        return []


def main():
    print('🔬 高量柱战法研究', flush=True)
    
    with open(WS / 'backtest' / 'v18_events_enriched.json') as f:
        events = json.load(f)['events']
    
    # 只测最近 events (D_t 在 4-1 ~ 4-30)
    recent_events = [e for e in events 
                     if e.get('d_t_date') and e['d_t_date'] >= '2026-04-01']
    print(f'  最近 events: {len(recent_events)}', flush=True)
    
    # 加载 K 线 cache
    cache = {}
    if CKPT.exists():
        with open(CKPT) as f:
            cache = json.load(f)
        print(f'  cache: {len(cache)} 只', flush=True)
    
    # 给每个事件计算高量柱特征
    enriched = []
    fail_cnt = 0
    for i, e in enumerate(recent_events):
        if i % 100 == 0:
            print(f'  [{i}/{len(recent_events)}] 处理中, 失败 {fail_cnt}', flush=True)
            # 中途存 cache
            if i > 0 and i % 500 == 0:
                with open(CKPT, 'w') as f:
                    json.dump(cache, f)
        
        code = e['code']
        d0 = e['d0_date']
        bars = get_kline(code, days=60, cache=cache)
        if not bars:
            fail_cnt += 1
            continue
        
        d0_idx = next((i for i, b in enumerate(bars) if b[0] == d0), -1)
        if d0_idx < 20:
            fail_cnt += 1
            continue
        
        try:
            pre20_vols = [float(b[5]) for b in bars[d0_idx-20:d0_idx]]
            pre60_vols = [float(b[5]) for b in bars[max(0, d0_idx-60):d0_idx]]
            d0_vol = float(bars[d0_idx][5])
            d0_high = float(bars[d0_idx][3])
            d0_low = float(bars[d0_idx][4])
            d0_close = float(bars[d0_idx][2])
            d0_open = float(bars[d0_idx][1])
            d0_prev_vol = pre20_vols[-1] if pre20_vols else 1
        except Exception:
            fail_cnt += 1
            continue
        
        # HVB 定义
        is_hvb_20 = d0_vol == max(pre20_vols + [d0_vol])
        is_hvb_60 = d0_vol == max(pre60_vols + [d0_vol]) if pre60_vols else False
        vol_ratio_prev = d0_vol / d0_prev_vol if d0_prev_vol > 0 else 0
        is_hvb_strong = is_hvb_20 and vol_ratio_prev >= 1.5
        
        # 高量柱倍数 (相对 20 天平均)
        avg_vol_20 = sum(pre20_vols) / max(1, len(pre20_vols))
        vol_mult = d0_vol / avg_vol_20 if avg_vol_20 > 0 else 0
        
        # D0 → D_t 之间最低价
        d_t = e['d_t_date']
        d_t_idx = next((i for i, b in enumerate(bars) if b[0] == d_t), -1)
        held_d0_low = None
        held_d0_close = None
        if d_t_idx > d0_idx:
            try:
                period_low = min(float(b[4]) for b in bars[d0_idx+1:d_t_idx+1])
                held_d0_low = period_low >= d0_low
                held_d0_close = period_low >= d0_close
            except Exception:
                pass
        
        # 实体阴/阳
        is_yang = d0_close >= d0_open
        body_pct = abs(d0_close - d0_open) / d0_open * 100
        upper_shadow = (d0_high - max(d0_close, d0_open)) / d0_open * 100
        lower_shadow = (min(d0_close, d0_open) - d0_low) / d0_open * 100
        
        feat = {
            'code': code,
            'd0_date': d0,
            'd_t_date': d_t,
            'outcome': e.get('outcome'),
            'd0_chg': e.get('d0_chg', 0),
            'd0_vol': d0_vol,
            'd0_low': d0_low,
            'd0_close': d0_close,
            'is_hvb_20': is_hvb_20,
            'is_hvb_60': is_hvb_60,
            'is_hvb_strong': is_hvb_strong,
            'vol_ratio_prev': vol_ratio_prev,
            'vol_mult_avg20': vol_mult,
            'held_d0_low': held_d0_low,
            'held_d0_close': held_d0_close,
            'is_yang': is_yang,
            'body_pct': body_pct,
            'upper_shadow': upper_shadow,
            'lower_shadow': lower_shadow,
        }
        enriched.append(feat)
        
        if i < len(recent_events) - 1:
            time.sleep(0.02)
    
    # 存 cache
    with open(CKPT, 'w') as f:
        json.dump(cache, f)
    
    print(f'\n📊 enriched events: {len(enriched)} (fail={fail_cnt})', flush=True)
    
    # 分析
    base = sum(1 for e in enriched if e['outcome'] == 'reversal') / max(1, len(enriched)) * 100
    print(f'\n=== Base rate ===', flush=True)
    print(f'  reversal: {base:.1f}% ({sum(1 for e in enriched if e["outcome"]=="reversal")}/{len(enriched)})', flush=True)
    
    print(f'\n=== H1: D0 is HVB ===', flush=True)
    for label, cond in [
        ('is_hvb_20', lambda e: e['is_hvb_20']),
        ('is_hvb_60', lambda e: e['is_hvb_60']),
        ('is_hvb_strong (20+1.5x)', lambda e: e['is_hvb_strong']),
        ('vol_mult ≥ 2.0', lambda e: e['vol_mult_avg20'] >= 2.0),
        ('vol_mult ≥ 3.0', lambda e: e['vol_mult_avg20'] >= 3.0),
        ('vol_mult ≥ 5.0', lambda e: e['vol_mult_avg20'] >= 5.0),
    ]:
        sub = [e for e in enriched if cond(e)]
        if sub:
            r = sum(1 for e in sub if e['outcome'] == 'reversal') / len(sub) * 100
            lift = r / base if base > 0 else 0
            print(f'  {label}: n={len(sub):>5}, reversal {r:.1f}%, lift {lift:.2f}x', flush=True)
    
    print(f'\n=== H2: HVB + 高量不破 ===', flush=True)
    for label, cond in [
        ('hvb_20 + held_d0_low', lambda e: e['is_hvb_20'] and e['held_d0_low']),
        ('hvb_strong + held_d0_low', lambda e: e['is_hvb_strong'] and e['held_d0_low']),
        ('hvb_20 + held_d0_close', lambda e: e['is_hvb_20'] and e['held_d0_close']),
        ('vol_mult≥3 + held_d0_low', lambda e: e['vol_mult_avg20']>=3 and e['held_d0_low']),
    ]:
        sub = [e for e in enriched if cond(e)]
        if sub:
            r = sum(1 for e in sub if e['outcome'] == 'reversal') / len(sub) * 100
            lift = r / base if base > 0 else 0
            print(f'  {label}: n={len(sub):>5}, reversal {r:.1f}%, lift {lift:.2f}x', flush=True)
    
    print(f'\n=== H3: HVB + D0 涨幅 ===', flush=True)
    for label, cond in [
        ('hvb_20 + d0_chg≥7', lambda e: e['is_hvb_20'] and e['d0_chg']>=7),
        ('hvb_20 + d0_chg≥9 (涨停)', lambda e: e['is_hvb_20'] and e['d0_chg']>=9.5),
        ('hvb_strong + d0_chg≥7', lambda e: e['is_hvb_strong'] and e['d0_chg']>=7),
        ('vol_mult≥3 + d0_chg≥9.5', lambda e: e['vol_mult_avg20']>=3 and e['d0_chg']>=9.5),
    ]:
        sub = [e for e in enriched if cond(e)]
        if sub:
            r = sum(1 for e in sub if e['outcome'] == 'reversal') / len(sub) * 100
            lift = r / base if base > 0 else 0
            print(f'  {label}: n={len(sub):>5}, reversal {r:.1f}%, lift {lift:.2f}x', flush=True)
    
    print(f'\n=== H4: 复合条件 (高量柱 + 不破 + 大阳) ===', flush=True)
    for label, cond in [
        ('hvb_strong + held_d0_low + d0_chg≥7', 
         lambda e: e['is_hvb_strong'] and e['held_d0_low'] and e['d0_chg']>=7),
        ('hvb_strong + held_d0_low + 大阳 (body≥3)', 
         lambda e: e['is_hvb_strong'] and e['held_d0_low'] and e['is_yang'] and e['body_pct']>=3),
        ('vol_mult≥3 + held_d0_low + d0_chg≥7', 
         lambda e: e['vol_mult_avg20']>=3 and e['held_d0_low'] and e['d0_chg']>=7),
    ]:
        sub = [e for e in enriched if cond(e)]
        if sub:
            r = sum(1 for e in sub if e['outcome'] == 'reversal') / len(sub) * 100
            lift = r / base if base > 0 else 0
            print(f'  {label}: n={len(sub):>5}, reversal {r:.1f}%, lift {lift:.2f}x', flush=True)
    
    # 落档
    out = WS / 'backtest' / 'hvb_research_results.json'
    with open(out, 'w') as f:
        json.dump({'base_rate': base, 'enriched': enriched}, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
