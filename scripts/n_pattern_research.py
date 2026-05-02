#!/usr/bin/env python3
"""N 字回踩战法研究

定义:
  P1 (起涨段 D-N ~ D-K):
    起点 P0_low = 起涨前低点
    P1_high = 起涨段最高点
    P1 涨幅 = (P1_high - P0_low) / P0_low ≥ 10%
  
  P2 (回调段 D-K ~ D0):
    P2_low = 回调段最低点
    回调幅度 = (P1_high - P2_low) / P1_high
    回调期 = K - 0 个交易日
  
  D0 (买入信号日):
    收盘站回 MA10
    量能 ≥ 前日
    P2_low > P0_low (高于起点 → N 字结构成立)

测试:
  - D+1 ~ D+5 是否再涨停?
  - 不同回调期 / 回调幅度 / P1 涨幅 → lift
"""
import json, urllib.request, time
from pathlib import Path
import warnings; warnings.filterwarnings('ignore')

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
CKPT = WS / 'backtest' / 'hvb_kline_cache.json'  # 复用


def is_zt_check(chg, code):
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    return chg >= (19 if is_20 else 9.5)


def find_n_patterns(bars, code):
    """对一只票的所有 K 找出 N 字形态"""
    if len(bars) < 30: return []
    patterns = []
    
    # MA10
    closes = [float(b[2]) for b in bars]
    ma10 = []
    for i in range(len(closes)):
        if i < 9:
            ma10.append(None)
        else:
            ma10.append(sum(closes[i-9:i+1]) / 10)
    
    # 对每个候选 D0 (从第 30 天起)
    for d0 in range(20, len(bars) - 5):
        try:
            d0_close = float(bars[d0][2])
            d0_open = float(bars[d0][1])
            d0_vol = float(bars[d0][5])
            d0_prev_vol = float(bars[d0-1][5])
            d0_prev_close = float(bars[d0-1][2])
            d0_chg = (d0_close - d0_prev_close) / d0_prev_close * 100
            
            # 1. D0 站上 MA10 (信号)
            if ma10[d0] is None: continue
            if d0_close < ma10[d0]: continue
            # 前一天还在 MA10 下 (突破信号)
            if ma10[d0-1] and float(bars[d0-1][2]) >= ma10[d0-1]: continue
            
            # 2. D0 量能 ≥ 前日 (放量启动)
            if d0_vol < d0_prev_vol * 1.1: continue
            
            # 3. D0 是阳柱
            if d0_close < d0_open: continue
            
            # 4. 找回调段 (D-1 ~ D-K, K ∈ [3, 10])
            # 回调段 = 从 P1_high 到 D0 之前
            # 找 D-3 ~ D-10 内的 P1_high
            best_p = None
            for k in range(3, 11):
                if d0 - k < 10: break
                # P1_high = max close in [d0-k-5, d0-k]
                p1_window_start = max(0, d0 - k - 5)
                p1_window_end = d0 - k
                if p1_window_end <= p1_window_start: continue
                
                p1_highs = [float(b[3]) for b in bars[p1_window_start:p1_window_end+1]]
                p1_high = max(p1_highs)
                p1_high_idx = p1_window_start + p1_highs.index(p1_high)
                
                # P0_low = min low in [p1_high_idx - 10, p1_high_idx] (起点)
                p0_window_start = max(0, p1_high_idx - 10)
                p0_lows = [float(b[4]) for b in bars[p0_window_start:p1_high_idx+1]]
                p0_low = min(p0_lows)
                
                p1_gain = (p1_high - p0_low) / p0_low * 100
                if p1_gain < 10: continue  # P1 涨幅不够
                
                # P2_low = min low between p1_high_idx and d0
                p2_lows = [float(b[4]) for b in bars[p1_high_idx+1:d0+1]]
                if not p2_lows: continue
                p2_low = min(p2_lows)
                p2_drop = (p1_high - p2_low) / p1_high * 100
                
                if p2_drop < 3 or p2_drop > 20: continue  # 回调 3-20%
                if p2_low <= p0_low: continue  # 必须高于起点 (N 字)
                
                best_p = {
                    'd0_idx': d0,
                    'd0_date': bars[d0][0],
                    'k_days': k,  # 回调天数
                    'p1_high': p1_high,
                    'p2_low': p2_low,
                    'p0_low': p0_low,
                    'p1_gain': p1_gain,
                    'p2_drop': p2_drop,
                    'd0_chg': d0_chg,
                    'd0_vol_ratio': d0_vol / d0_prev_vol,
                }
                break  # 找到最近的就行
            
            if not best_p: continue
            
            # D+1 ~ D+5 是否涨停?
            future_5 = bars[d0+1:d0+6]
            if len(future_5) < 5: continue
            
            fut_zt = False
            fut_zt_day = -1
            fut_max_chg = -100
            for j, b in enumerate(future_5):
                prev = float(future_5[j-1][2]) if j > 0 else d0_close
                fut_chg = (float(b[2]) - prev) / prev * 100
                fut_max_chg = max(fut_max_chg, fut_chg)
                if is_zt_check(fut_chg, code):
                    fut_zt = True
                    fut_zt_day = j + 1
                    break
            
            # D+5 总涨幅
            d5_chg = (float(future_5[-1][2]) - d0_close) / d0_close * 100
            
            best_p.update({
                'code': code,
                'fut_zt_5d': fut_zt,
                'fut_zt_day': fut_zt_day if fut_zt else None,
                'fut_max_chg': fut_max_chg,
                'd5_total_chg': d5_chg,
            })
            patterns.append(best_p)
        except Exception:
            continue
    
    return patterns


def main():
    print('🔬 N 字回踩战法研究', flush=True)
    
    if not CKPT.exists():
        print('❌ 没 K 线 cache')
        return
    with open(CKPT) as f:
        cache = json.load(f)
    print(f'  K 线 cache: {len(cache)} 只', flush=True)
    
    all_patterns = []
    for code, bars in cache.items():
        ps = find_n_patterns(bars, code)
        all_patterns.extend(ps)
    
    print(f'  N 字形态: {len(all_patterns)}', flush=True)
    
    if not all_patterns:
        print('❌ 没找到 N 字形态')
        return
    
    base = sum(1 for p in all_patterns if p['fut_zt_5d']) / len(all_patterns) * 100
    avg_d5 = sum(p['d5_total_chg'] for p in all_patterns) / len(all_patterns)
    print(f'\n=== 基线 ===', flush=True)
    print(f'  5 天涨停率: {base:.1f}%', flush=True)
    print(f'  D+5 平均涨幅: {avg_d5:+.2f}%', flush=True)
    
    print(f'\n=== H1: P1 涨幅 ===', flush=True)
    for thr in [10, 15, 20, 30]:
        sub = [p for p in all_patterns if p['p1_gain'] >= thr]
        if sub:
            r = sum(1 for p in sub if p['fut_zt_5d']) / len(sub) * 100
            avg = sum(p['d5_total_chg'] for p in sub) / len(sub)
            print(f'  P1≥{thr}%: n={len(sub):>4}, 涨停 {r:.1f}%, 平均涨幅 {avg:+.2f}%', flush=True)
    
    print(f'\n=== H2: 回调幅度 ===', flush=True)
    for label, lo, hi in [('小调 3-7%', 3, 7), ('中调 7-12%', 7, 12), ('深调 12-20%', 12, 20)]:
        sub = [p for p in all_patterns if lo <= p['p2_drop'] < hi]
        if sub:
            r = sum(1 for p in sub if p['fut_zt_5d']) / len(sub) * 100
            avg = sum(p['d5_total_chg'] for p in sub) / len(sub)
            print(f'  {label}: n={len(sub):>4}, 涨停 {r:.1f}%, 平均涨幅 {avg:+.2f}%', flush=True)
    
    print(f'\n=== H3: 回调天数 ===', flush=True)
    for label, lo, hi in [('短 3-5d', 3, 5), ('中 5-8d', 5, 8), ('长 8-10d', 8, 11)]:
        sub = [p for p in all_patterns if lo <= p['k_days'] < hi]
        if sub:
            r = sum(1 for p in sub if p['fut_zt_5d']) / len(sub) * 100
            avg = sum(p['d5_total_chg'] for p in sub) / len(sub)
            print(f'  {label}: n={len(sub):>4}, 涨停 {r:.1f}%, 平均涨幅 {avg:+.2f}%', flush=True)
    
    print(f'\n=== H4: D0 量比 ===', flush=True)
    for thr in [1.1, 1.5, 2, 3]:
        sub = [p for p in all_patterns if p['d0_vol_ratio'] >= thr]
        if sub:
            r = sum(1 for p in sub if p['fut_zt_5d']) / len(sub) * 100
            avg = sum(p['d5_total_chg'] for p in sub) / len(sub)
            print(f'  D0_vol≥{thr}x: n={len(sub):>4}, 涨停 {r:.1f}%, 平均涨幅 {avg:+.2f}%', flush=True)
    
    print(f'\n=== H5: 复合最强 ===', flush=True)
    for label, cond in [
        ('P1≥15 + 中调 7-12 + D0_vol≥1.5', 
         lambda p: p['p1_gain']>=15 and 7<=p['p2_drop']<12 and p['d0_vol_ratio']>=1.5),
        ('P1≥10 + 短调 3-5d + D0_vol≥2', 
         lambda p: p['p1_gain']>=10 and p['k_days']<=5 and p['d0_vol_ratio']>=2),
        ('P1≥20 + D0 阳量 + 回调≤10%', 
         lambda p: p['p1_gain']>=20 and p['d0_vol_ratio']>=1.5 and p['p2_drop']<=10),
    ]:
        sub = [p for p in all_patterns if cond(p)]
        if sub:
            r = sum(1 for p in sub if p['fut_zt_5d']) / len(sub) * 100
            avg = sum(p['d5_total_chg'] for p in sub) / len(sub)
            print(f'  {label}: n={len(sub):>4}, 涨停 {r:.1f}%, 平均涨幅 {avg:+.2f}%', flush=True)
    
    out = WS / 'backtest' / 'n_pattern_research_results.json'
    with open(out, 'w') as f:
        json.dump({'base_rate': base, 'avg_d5': avg_d5, 'patterns': all_patterns}, 
                  f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
