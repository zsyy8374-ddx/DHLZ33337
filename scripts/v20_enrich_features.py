#!/usr/bin/env python3
"""v2.0 特征增强 — 给 v18_events 加新特征
新特征:
  HVB 类:
    - hvb_d0_vol_mult_20: D0 成交量 / 20日均量
    - hvb_d0_is_max_20: D0 是否 20 天最大量 (0/1)
    - hvb_d0_vol_ratio_prev: D0 成交量 / 前日
    - hvb_d0_yang: D0 是否阳柱
    - hvb_d0_body_pct: D0 实体 %
    
  N 字结构 (D0 之前的趋势):
    - n_p1_gain: 前期 P1 涨幅 (10 天前最高 vs 起点低点)
    - n_p2_drop: D0 前的回调幅度
    - n_in_n_pattern: 是否处于 N 字结构 (0/1)
    
  价格相对位置:
    - price_vs_ma10: D0 收盘 / MA10 - 1
    - price_vs_ma20: D0 收盘 / MA20 - 1
    - price_vs_ma60: D0 收盘 / MA60 - 1
    - dist_from_60d_high: D0 距 60 天最高 %
"""
import json, urllib.request, time
from pathlib import Path
import warnings; warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
SRC = WS / 'backtest' / 'v18_events_enriched.json'
OUT = WS / 'backtest' / 'v20_events_enriched.json'
KCACHE = WS / 'backtest' / 'hvb_kline_cache.json'


def get_kline_cached(code, cache):
    if code in cache:
        return cache[code]
    prefix = 'sh' if code.startswith('6') else 'sz'
    url = f'http://web.ifzq.gtimg.cn/appstock/app/newfqkline/get?param={prefix}{code},day,,,500,qfq'
    try:
        req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.loads(r.read().decode())
        bars = d.get('data', {}).get(f'{prefix}{code}', {}).get('qfqday', [])
        cache[code] = bars
        return bars
    except: return []


def compute_v20_features(bars, d0_idx):
    """给定 K 线和 D0 索引, 返回新特征 dict"""
    if d0_idx < 20: return None
    try:
        d0_close = float(bars[d0_idx][2])
        d0_open = float(bars[d0_idx][1])
        d0_high = float(bars[d0_idx][3])
        d0_low = float(bars[d0_idx][4])
        d0_vol = float(bars[d0_idx][5])
        d0_prev_vol = float(bars[d0_idx-1][5])
        
        # 1. HVB
        pre20_vols = [float(bars[i][5]) for i in range(d0_idx-20, d0_idx)]
        avg_vol_20 = sum(pre20_vols) / 20 if pre20_vols else 1
        hvb_d0_vol_mult_20 = d0_vol / avg_vol_20 if avg_vol_20 > 0 else 0
        hvb_d0_is_max_20 = 1 if d0_vol >= max(pre20_vols + [d0_vol]) else 0
        hvb_d0_vol_ratio_prev = d0_vol / d0_prev_vol if d0_prev_vol > 0 else 0
        hvb_d0_yang = 1 if d0_close >= d0_open else 0
        hvb_d0_body_pct = abs(d0_close - d0_open) / max(d0_open, 0.01) * 100
        
        # 2. N 字结构 (找前 3-10 天有没有形成 N 字)
        n_p1_gain = 0
        n_p2_drop = 0
        n_in_n_pattern = 0
        for k in range(3, 11):
            if d0_idx - k < 5: break
            p1_window = [float(bars[i][3]) for i in range(max(0, d0_idx-k-5), d0_idx-k+1)]
            if not p1_window: continue
            p1_high = max(p1_window)
            p1_high_idx = p1_window.index(p1_high) + max(0, d0_idx-k-5)
            
            p0_lows = [float(bars[i][4]) for i in range(max(0, p1_high_idx-10), p1_high_idx+1)]
            if not p0_lows: continue
            p0_low = min(p0_lows)
            p1_g = (p1_high - p0_low) / max(p0_low, 0.01) * 100
            
            p2_lows = [float(bars[i][4]) for i in range(p1_high_idx+1, d0_idx+1)]
            if not p2_lows: continue
            p2_low = min(p2_lows)
            p2_d = (p1_high - p2_low) / max(p1_high, 0.01) * 100
            
            if p1_g >= 10 and 3 <= p2_d <= 20 and p2_low > p0_low:
                n_p1_gain = max(n_p1_gain, p1_g)
                n_p2_drop = max(n_p2_drop, p2_d)
                n_in_n_pattern = 1
                break
        
        # 3. 均线相对位置
        if d0_idx >= 9:
            ma10 = sum(float(bars[i][2]) for i in range(d0_idx-9, d0_idx+1)) / 10
            price_vs_ma10 = (d0_close - ma10) / ma10 * 100
        else:
            price_vs_ma10 = 0
        
        if d0_idx >= 19:
            ma20 = sum(float(bars[i][2]) for i in range(d0_idx-19, d0_idx+1)) / 20
            price_vs_ma20 = (d0_close - ma20) / ma20 * 100
        else:
            price_vs_ma20 = 0
        
        if d0_idx >= 59:
            ma60 = sum(float(bars[i][2]) for i in range(d0_idx-59, d0_idx+1)) / 60
            price_vs_ma60 = (d0_close - ma60) / ma60 * 100
        else:
            price_vs_ma60 = 0
        
        # 4. 距 60 天最高
        if d0_idx >= 59:
            high_60d = max(float(bars[i][3]) for i in range(d0_idx-59, d0_idx+1))
            dist_from_60d_high = (high_60d - d0_close) / max(high_60d, 0.01) * 100
        else:
            dist_from_60d_high = 0
        
        return {
            'hvb_d0_vol_mult_20': hvb_d0_vol_mult_20,
            'hvb_d0_is_max_20': hvb_d0_is_max_20,
            'hvb_d0_vol_ratio_prev': hvb_d0_vol_ratio_prev,
            'hvb_d0_yang': hvb_d0_yang,
            'hvb_d0_body_pct': hvb_d0_body_pct,
            'n_p1_gain': n_p1_gain,
            'n_p2_drop': n_p2_drop,
            'n_in_n_pattern': n_in_n_pattern,
            'price_vs_ma10': price_vs_ma10,
            'price_vs_ma20': price_vs_ma20,
            'price_vs_ma60': price_vs_ma60,
            'dist_from_60d_high': dist_from_60d_high,
        }
    except: return None


def main():
    print('🔬 v2.0 特征增强', flush=True)
    
    with open(SRC) as f:
        data = json.load(f)
    events = data['events']
    print(f'  events: {len(events)}', flush=True)
    
    cache = {}
    if KCACHE.exists():
        with open(KCACHE) as f:
            cache = json.load(f)
        print(f'  K cache: {len(cache)} 只', flush=True)
    
    enriched = 0
    fail = 0
    for i, e in enumerate(events):
        if i % 200 == 0:
            print(f'  [{i}/{len(events)}] enriched={enriched} fail={fail}', flush=True)
            if i > 0 and i % 500 == 0:
                with open(KCACHE, 'w') as f:
                    json.dump(cache, f)
        
        bars = get_kline_cached(e['code'], cache)
        if not bars:
            fail += 1
            continue
        
        d0_idx = next((j for j, b in enumerate(bars) if b[0] == e['d0_date']), -1)
        if d0_idx < 20:
            fail += 1
            continue
        
        feats = compute_v20_features(bars, d0_idx)
        if feats:
            e.update(feats)
            enriched += 1
        else:
            fail += 1
        
        if e['code'] not in cache:
            time.sleep(0.02)
    
    with open(KCACHE, 'w') as f:
        json.dump(cache, f)
    
    print(f'\n📊 enriched: {enriched}, fail: {fail}', flush=True)
    
    with open(OUT, 'w') as f:
        json.dump({'events': events}, f, ensure_ascii=False, indent=2)
    print(f'💾 落档: {OUT}', flush=True)


if __name__ == '__main__':
    main()
