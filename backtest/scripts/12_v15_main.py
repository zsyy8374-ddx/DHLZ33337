"""
v15: 强力突破 + 板块强度 + 能量释放 (主升浪起点终极版)
核心逻辑:
1. v15.0: v10.0 + 涨停基因 (最近10日必须有涨停)
2. v15.1: v10.0 + 板块强度 (今日所属行业板块平均涨幅前30%)
3. v15.2: v10.0 + OBV能量释放 (OBV 创 60 日新高)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def calc_obv(bars):
    obv = [0]
    for i in range(1, len(bars)):
        if bars[i]['c'] > bars[i-1]['c']:
            obv.append(obv[-1] + bars[i]['v'])
        elif bars[i]['c'] < bars[i-1]['c']:
            obv.append(obv[-1] - bars[i]['v'])
        else:
            obv.append(obv[-1])
    return obv

def f_v10_0_core(bars, today, mkt):
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 6.0): return False, 0, {} # 稍微放宽主升浪当天的涨幅
    
    ma20=ma(closes,20); ma60=ma(closes,60)
    vol20=ma(vols,20)
    if not all([ma20,ma60,vol20]): return False, 0, {}
    if c <= ma20: return False, 0, {}
    
    # VCP 核心 (波动收缩)
    w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
    w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
    if w2 >= w1 * 0.9: return False, 0, {}
    
    return True, 10, {'vcp': w2/w1}

def f_v15_0_gene(bars, today, mkt):
    """v15.0: v10.0 + 涨停基因 (主升浪的种子里必须有涨停)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    # 检查过去 20 天是否有过涨停 (涨幅 > 9.8%)
    has_limit = False
    for i in range(1, len(bars)):
        prev = bars[i-1]['c']
        curr = bars[i]['c']
        if (curr/prev - 1) > 0.098:
            has_limit = True
            break
    
    if not has_limit: return False, s, dbg
    return True, s, dbg

def f_v15_1_obv(bars, today, mkt):
    """v15.1: v10.0 + OBV 能量释放 (资金抢筹证明)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    obv_hist = calc_obv(bars)
    # 计算今日 OBV
    prev_obv = obv_hist[-1]
    today_obv = prev_obv + today['v'] if today['c'] > bars[-1]['c'] else prev_obv - today['v']
    
    # 检查今日 OBV 是否创 60 日新高
    if today_obv <= max(obv_hist[-60:]): return False, s, dbg
    
    return True, s, dbg

def backtest(formula_fn, klines, eval_dates):
    hits = []
    for code, bars in klines.items():
        d_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in d_idx: continue
            i = d_idx[d]
            if i < 65 or i+20 >= len(bars): continue
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
    
    for name, fn in [('v10_Ref', f_v10_0_core), ('v15.0_Limit', f_v15_0_gene), ('v15.1_OBV', f_v15_1_obv)]:
        hits = backtest(fn, klines, eval_dates)
        if not hits: continue
        r20 = [h['ret20'] for h in hits]
        win20 = sum(1 for r in r20 if r>0)/len(r20)*100
        print(f"{name:<12}: 命中={len(hits):<5} T+20均={statistics.mean(r20):.2f}%  T+20胜={win20:.1f}%")

if __name__ == "__main__": main()
