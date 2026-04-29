"""
v12: 筹码全胜 + 深度洗盘 + 获利盘占比
1. v12.0: v10.0 + 获利比例(估算) > 85%
2. v12.1: v10.0 + 深度整理(MA60上行且时间>20天)
3. v12.2: v10.0 + 筹码集中(10%空间内筹码占比)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def estimate_profit_ratio(bars, price):
    """
    通过过去 120 天的量价分布, 粗略估算获利盘比例
    这在 Python 中模拟筹码分布
    """
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
    c=today['c']; h=today['h']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4.5): return False, 0, {}
    
    ma20=ma(closes,20); ma60=ma(closes,60)
    vol20=ma(vols,20)
    if not all([ma20,ma60,vol20]): return False, 0, {}
    if c <= ma20: return False, 0, {}
    
    # VCP 核心 (v10.0)
    w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
    w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
    if w2 >= w1 * 0.9: return False, 0, {}
    
    # 其它 v9.4 核心
    if c < hhv(highs[-20:], 20) * 0.99: return False, 0, {}
    
    return True, 10, {'vcp': w2/w1}

def f_v12_0_profit(bars, today, mkt):
    """v12.0: v10.0 + 获利盘估算 > 85%"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    ratio = estimate_profit_ratio(bars, today['c'])
    if ratio < 0.85: return False, s, dbg
    return True, s, dict(dbg, profit_ratio=ratio)

def f_v12_1_duration(bars, today, mkt):
    """v12.1: v10.0 + 深度洗盘时间 (>25天都在MA60之上)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    closes = [b['c'] for b in bars]
    ma60s = [ma(closes[:i+1], 60) for i in range(len(closes)-30, len(closes))]
    # 检查最近 30 天是否都在 MA60 之上
    above_count = sum(1 for i in range(30) if closes[-(30-i)] > ma60s[i])
    if above_count < 28: return False, s, dbg
    
    return True, s, dbg

def f_v12_2_ultimate(bars, today, mkt):
    """v12.2: v12.0 + v12.1 终极合体"""
    p, s, dbg = f_v12_0_profit(bars, today, mkt)
    if not p: return False, s, dbg
    return f_v12_1_duration(bars, today, mkt)

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
    print("加载全样本数据 (含120天预热)...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {}
    for f in files:
        with open(f) as j: klines[os.path.basename(f).replace('.json','')] = json.load(j)
    
    dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))
    eval_dates = dates[max(0, len(dates)-120):-22]
    
    for name, fn in [('v10.0_Ref', f_v10_0_core), ('v12.0_Profit', f_v12_0_profit), ('v12.1_Dur', f_v12_1_duration), ('v12.2_Ulti', f_v12_2_ultimate)]:
        hits = backtest(fn, klines, eval_dates)
        if not hits: continue
        r20 = [h['ret20'] for h in hits]
        win20 = sum(1 for r in r20 if r>0)/len(r20)*100
        print(f"{name:<12}: 命中={len(hits):<5} T+20均={statistics.mean(r20):.2f}%  T+20胜={win20:.1f}%")

if __name__ == "__main__": main()
