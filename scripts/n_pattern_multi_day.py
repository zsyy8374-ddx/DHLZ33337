#!/usr/bin/env python3
"""N 字回踩 多日回测 (4-21 ~ 4-30)

用 v18 K 线 cache (344 只) + 全市场 wencai 单日数据
对每个 D0 (4-21, 4-22, ..., 4-29) 跑一遍, 看 D+1 涨停率

策略对比:
  方案 A: 用 hvb_kline_cache 跑 — 但池子有偏 (都是涨停过的票)
  方案 B: 用 wencai 拉每天全市场 量比≥1.1 池子, 然后挨个拉 K — 但很慢
  
  本脚本: 用方案 A, 因为 cache 已有, 但坦白这是有偏样本
  Lift 解读时要用 cache 池里的全部 D+1 涨停率作基线
"""
import json, urllib.request, time
from pathlib import Path
import warnings; warnings.filterwarnings('ignore')
from collections import defaultdict
from datetime import datetime, timedelta

WS = Path('/Users/openclaw/.openclaw/workspace-dengxian')
CKPT = WS / 'backtest' / 'hvb_kline_cache.json'


def is_zt_check(chg, code):
    is_20 = code.startswith('300') or code.startswith('301') or code.startswith('688') or code.startswith('689')
    return chg >= (19 if is_20 else 9.5)


def find_n_at(bars, d0_idx, code):
    """检查 d0 是否符合 N 字, 返回 dict 或 None"""
    if d0_idx < 15: return None
    try:
        d0_close = float(bars[d0_idx][2])
        d0_open = float(bars[d0_idx][1])
        d0_vol = float(bars[d0_idx][5])
        d0_prev_close = float(bars[d0_idx-1][2])
        d0_prev_vol = float(bars[d0_idx-1][5])
        d0_chg = (d0_close - d0_prev_close) / d0_prev_close * 100
        
        # D0 是阳柱
        if d0_close < d0_open: return None
        # 排除涨停
        if is_zt_check(d0_chg, code): return None
        # 量比 ≥ 1.1
        if d0_prev_vol > 0 and d0_vol < d0_prev_vol * 1.1: return None
        # 涨幅 [0, 9.5)
        if d0_chg < 0: return None
        
        # MA10
        closes = [float(bars[i][2]) for i in range(d0_idx-9, d0_idx+1)]
        ma10_d0 = sum(closes) / 10
        if d0_close < ma10_d0: return None
        prev_closes = [float(bars[i][2]) for i in range(d0_idx-10, d0_idx)]
        ma10_prev = sum(prev_closes) / 10
        if float(bars[d0_idx-1][2]) >= ma10_prev: return None
        
        # 找 N 字结构
        for k in range(3, 11):
            if d0_idx - k < 5: break
            p1_window_start = max(0, d0_idx - k - 5)
            p1_window_end = d0_idx - k
            p1_highs = [float(bars[i][3]) for i in range(p1_window_start, p1_window_end+1)]
            if not p1_highs: continue
            p1_high = max(p1_highs)
            p1_high_idx = p1_window_start + p1_highs.index(p1_high)
            
            p0_window_start = max(0, p1_high_idx - 10)
            p0_lows = [float(bars[i][4]) for i in range(p0_window_start, p1_high_idx+1)]
            if not p0_lows: continue
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
                'd0_idx': d0_idx,
                'd0_chg': d0_chg,
                'd0_vol_ratio': d0_vol / d0_prev_vol if d0_prev_vol > 0 else 0,
                'p1_gain': p1_gain,
                'p2_drop': p2_drop,
                'k_days': k,
                'd0_close': d0_close,
            }
    except: pass
    return None


def main():
    print('🔬 N 字多日回测 (用 K 线 cache)', flush=True)
    
    if not CKPT.exists():
        print('❌ cache 不存在')
        return
    with open(CKPT) as f:
        cache = json.load(f)
    print(f'  K 线池: {len(cache)} 只 (来自 v18 events)', flush=True)
    
    # 目标 D0 列表 (北京交易日 4-21 ~ 4-29)
    target_d0_list = ['2026-04-21', '2026-04-22', '2026-04-23', '2026-04-24', 
                      '2026-04-25', '2026-04-28', '2026-04-29']
    # 4-25 是周六, 4-26 周日 — 但 K 线只会有交易日, 我们检查时跳过
    
    by_day = defaultdict(list)
    pool_d_p1_zt = defaultdict(lambda: [0, 0])  # day -> [zt_count, total]
    
    for code, bars in cache.items():
        if len(bars) < 25: continue
        # 给每只票, 找每个 target_d0 的 N 字
        for target in target_d0_list:
            d0_idx = next((i for i, b in enumerate(bars) if b[0] == target), -1)
            if d0_idx < 15: continue
            if d0_idx + 1 >= len(bars): continue
            
            # 池子 base rate: D+1 涨停率 (在这只票上, 这个 D0 后是否涨停)
            d0_close = float(bars[d0_idx][2])
            d1 = bars[d0_idx + 1]
            d1_close = float(d1[2])
            d1_chg = (d1_close - d0_close) / d0_close * 100
            d1_zt = is_zt_check(d1_chg, code)
            pool_d_p1_zt[target][0] += 1 if d1_zt else 0
            pool_d_p1_zt[target][1] += 1
            
            # 找 N 字
            p = find_n_at(bars, d0_idx, code)
            if p:
                p['d0_date'] = target
                p['d1_chg'] = d1_chg
                p['d1_zt'] = d1_zt
                p['d1_date'] = d1[0]
                by_day[target].append(p)
    
    # 统计
    print(f'\n=== 各天 N 字数量 + 命中 ===', flush=True)
    print(f'{"日期":<12} {"池里":>5} {"池基线":>8} {"N字":>5} {"N字涨停":>10} {"N字Lift":>8}', flush=True)
    
    all_patterns = []
    for d in target_d0_list:
        ps = by_day.get(d, [])
        pool_zt, pool_n = pool_d_p1_zt[d]
        pool_base = pool_zt / max(1, pool_n) * 100
        if not ps:
            print(f'{d:<12} {pool_n:>5} {pool_base:>7.1f}% {0:>5} {"-":>10} {"-":>8}')
            continue
        zt_n = sum(1 for p in ps if p['d1_zt'])
        zt_rate = zt_n / len(ps) * 100
        lift = zt_rate / pool_base if pool_base > 0 else 0
        print(f'{d:<12} {pool_n:>5} {pool_base:>7.1f}% {len(ps):>5} {zt_rate:>7.1f}% ({zt_n:>2}) {lift:>7.2f}x', flush=True)
        all_patterns.extend(ps)
    
    # 总体
    if all_patterns:
        total_zt = sum(1 for p in all_patterns if p['d1_zt'])
        total_rate = total_zt / len(all_patterns) * 100
        total_pool_zt = sum(v[0] for v in pool_d_p1_zt.values())
        total_pool_n = sum(v[1] for v in pool_d_p1_zt.values())
        total_pool_base = total_pool_zt / max(1, total_pool_n) * 100
        total_lift = total_rate / total_pool_base if total_pool_base > 0 else 0
        print(f'\n=== 多日合计 ===', flush=True)
        print(f'  N 字: {len(all_patterns)} 个事件', flush=True)
        print(f'  D+1 涨停: {total_zt} = {total_rate:.1f}%', flush=True)
        print(f'  池子 base: {total_pool_base:.1f}%', flush=True)
        print(f'  Lift vs 池: {total_lift:.2f}x', flush=True)
        
        # 复合条件
        print(f'\n=== 复合: P1≥15 + 深调 12-20 ===', flush=True)
        sub = [p for p in all_patterns if p['p1_gain']>=15 and p['p2_drop']>=12]
        if sub:
            r = sum(1 for p in sub if p['d1_zt']) / len(sub) * 100
            lift = r / total_pool_base if total_pool_base > 0 else 0
            print(f'  n={len(sub)}, 涨停 {r:.1f}%, lift {lift:.2f}x', flush=True)
        
        # 复合: 大 P1
        print(f'\n=== H: P1≥30 (强势) ===', flush=True)
        sub = [p for p in all_patterns if p['p1_gain']>=30]
        if sub:
            r = sum(1 for p in sub if p['d1_zt']) / len(sub) * 100
            lift = r / total_pool_base if total_pool_base > 0 else 0
            print(f'  n={len(sub)}, 涨停 {r:.1f}%, lift {lift:.2f}x', flush=True)
        
        # 不同回调幅度
        print(f'\n=== 回调幅度 (合计) ===', flush=True)
        for label, lo, hi in [('小调 3-7%', 3, 7), ('中调 7-12%', 7, 12), ('深调 12-20%', 12, 20.01)]:
            sub = [p for p in all_patterns if lo <= p['p2_drop'] < hi]
            if sub:
                r = sum(1 for p in sub if p['d1_zt']) / len(sub) * 100
                lift = r / total_pool_base if total_pool_base > 0 else 0
                print(f'  {label}: n={len(sub)}, 涨停 {r:.1f}%, lift {lift:.2f}x', flush=True)
    
    out = WS / 'backtest' / 'n_pattern_multi_day.json'
    with open(out, 'w') as f:
        json.dump({'patterns': all_patterns, 'pool_base_by_day': dict(pool_d_p1_zt)}, 
                  f, ensure_ascii=False, indent=2)
    print(f'\n💾 落档: {out}', flush=True)


if __name__ == '__main__':
    main()
