"""
v13: 黄金坑 (Golden Pit) + 动量反转 + 筹码搬家
1. v13.0: v10.0 + 黄金坑 (5日内曾跌破MA20但今日强力收回)
2. v13.1: v10.0 + 筹码搬家 (获利盘从<50% 突增至 >70%)
3. v13.2: v13.0 + 极度缩量回调 (坑中量极小)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def estimate_profit_ratio(bars, price):
    if len(bars) < 60: return 0.5
    recent_bars = bars[-120:]
    total_vol = sum(b['v'] for b in recent_bars)
    if total_vol == 0: return 0.5
    profit_vol = sum(b['v'] for b in recent_bars if b['c'] <= price)
    return profit_vol / total_vol

def f_v10_0_core(bars, today, mkt):
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 5.0): return False, 0, {}
    
    ma20=ma(closes,20); ma60=ma(closes,60)
    vol20=ma(vols,20)
    if not all([ma20,ma60,vol20]): return False, 0, {}
    if c <= ma20: return False, 0, {}
    
    w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
    w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
    if w2 >= w1 * 0.95: return False, 0, {} # 略微放宽VCP以容纳黄金坑
    
    return True, 10, {'vcp': w2/w1}

def f_v13_0_pit(bars, today, mkt):
    """v13.0: v10.0 + 黄金坑 (5日内曾跌破MA20但今日收回)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    closes = [b['c'] for b in bars]
    # 检查过去 5 天是否有收盘价低于当时的 MA20
    had_pit = False
    for i in range(1, 6):
        idx = len(closes) - i
        curr_ma20 = ma(closes[:idx+1], 20)
        if curr_ma20 and closes[idx] < curr_ma20:
            had_pit = True
            break
    
    if not had_pit: return False, s, dbg
    return True, s, dbg

def f_v13_1_moving(bars, today, mkt):
    """v13.1: v10.0 + 筹码搬家 (获利盘显著增长)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    ratio_now = estimate_profit_ratio(bars, today['c'])
    ratio_5d = estimate_profit_ratio(bars[:-5], bars[-5]['c'])
    
    # 获利盘必须从相对低位(主力吸筹)跳升到强势位(主力拉升)
    if not (ratio_5d < 0.6 and ratio_now > 0.75): return False, s, dbg
    
    return True, s, dict(dbg, shift=ratio_now-ratio_5d)

def f_v13_2_dry_pit(bars, today, mkt):
    """v13.2: 黄金坑 + 坑中极度缩量"""
    p, s, dbg = f_v13_0_pit(bars, today, mkt)
    if not p: return False, s, dbg
    
    vols = [b['v'] for b in bars]
    vol20 = ma(vols, 20)
    # 坑底(跌破MA20那天)的量必须是缩量的
    if not any(v < vol20 * 0.7 for v in vols[-5:]): return False, s, dbg
    
    return True, s, dbg

def backtest(formula_fn, klines, eval_dates):
    hits = []
    for code, bars in klines.items():
        d_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in d_idx: continue
            i = d_idx[d]
            if i < 125 or i+20 >= len(bars): continue
            passed, s, dbg = formula_fn(bars[:i], bars[i], None)
            if not passed: continue
            entry = bars[i+1]['o']
            hits.append({
                'date': d, 'code': code,
                'ret10': (bars[i+10]['c']/entry-1)*100,
                'ret20': (bars[i+20]['c']/entry-1)*100
            })
    return hits

def main():
    import glob, statistics
    print("加载数据...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {os.path.basename(f).replace('.json',''): json.load(open(f)) for f in files}
    
    dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))
    eval_dates = dates[max(0, len(dates)-150):-22]
    
    for name, fn in [('v10_Ref', f_v10_0_core), ('v13.0_Pit', f_v13_0_pit), ('v13.1_Move', f_v13_1_moving), ('v13.2_DryPit', f_v13_2_dry_pit)]:
        hits = backtest(fn, klines, eval_dates)
        if not hits: continue
        r20 = [h['ret20'] for h in hits]
        win20 = sum(1 for r in r20 if r>0)/len(r20)*100
        print(f"{name:<12}: 命中={len(hits):<5} T+20均={statistics.mean(r20):.2f}%  T+20胜={win20:.1f}%")

if __name__ == "__main__": main()
