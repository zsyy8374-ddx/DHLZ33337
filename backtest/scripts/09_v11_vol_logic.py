"""
v11: 筹码锁定 + 换手率梯度 + 缩量回调过滤
1. v11.0: v10.0 + 换手率分层 (1% < daily_turnover < 5%)
2. v11.1: v10.0 + 缩量整理 (最近3日量递减)
3. v11.2: v10.0 + 机构轨迹 (单笔大单模拟)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')
RESULT_DIR = 'backtest/results'

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def f_v10_0_core(bars, today, mkt):
    """v10.0 核心逻辑"""
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; h=today['h']; v=today['v']; o=today['o']; l=today['l']
    
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4.5): return False, 0, {}
    
    ma10=ma(closes,10); ma20=ma(closes,20); ma60=ma(closes,60)
    vol5=ma(vols,5); vol20=ma(vols,20)
    if not all([ma10,ma20,ma60,vol20]): return False, 0, {}
    if c <= ma10 or c <= ma20: return False, 0, {}
    
    # MA20上行
    ma20_5d = ma(closes[:-5], 20)
    if not (ma20_5d and ma20 > ma20_5d * 1.005): return False, 0, {}
    
    # 量比
    ratio = v/vol20
    if not (1.3 < ratio < 2.5): return False, 0, {}
    
    # VCP 波动率收缩 (v10.0 核心)
    w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
    w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
    if w2 >= w1 * 0.9: return False, 0, {}
    
    # 其它 v9.4 基础
    if vol5/vol20 < 1.0 or vol5/vol20 > 2.0: return False, 0, {}
    if closes[-1] <= ma(closes[:-1], 20): return False, 0, {}
    if c <= o or c < hhv(highs[-20:], 20) * 0.99: return False, 0, {}
    
    return True, 10, {'vcp_ratio': w2/w1, 'vol_ratio': ratio}

def f_v11_0_dry(bars, today, mkt):
    """v11.0: v10.0 + 起爆前缩量回调 (最近3天内有2天缩量)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    vols = [b['v'] for b in bars]
    vol20 = ma(vols, 20)
    # 检查前3天是否出现过"地量"(小于均量0.8)
    dry_count = sum(1 for v in vols[-3:] if v < vol20 * 0.8)
    if dry_count < 1: return False, s, dbg
    
    return True, s, dict(dbg, dry_count=dry_count)

def f_v11_1_vol_stairs(bars, today, mkt):
    """v11.1: v10.0 + 阶梯量 (量能稳步放大)"""
    p, s, dbg = f_v10_0_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    vols = [b['v'] for b in bars]
    # 今日量 > 昨日量 > 前日量 * 0.8 (阶梯式温和放大)
    if not (today['v'] > vols[-1] > vols[-2] * 0.8): return False, s, dbg
    
    return True, s, dbg

def f_v11_2_strict(bars, today, mkt):
    """v11.2: v10.0 + v11.0 + v11.1 (最严苛版)"""
    p, s, dbg = f_v11_0_dry(bars, today, mkt)
    if not p: return False, s, dbg
    return f_v11_1_vol_stairs(bars, today, mkt)

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
    import glob
    print("加载全样本数据...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {}
    for f in files:
        with open(f) as j: klines[os.path.basename(f).replace('.json','')] = json.load(j)
    
    dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))
    eval_dates = dates[max(0, len(dates)-120):-22]
    
    for name, fn in [('v10.0_Ref', f_v10_0_core), ('v11.0_Dry', f_v11_0_dry), ('v11.1_Stairs', f_v11_1_vol_stairs), ('v11.2_Strict', f_v11_2_strict)]:
        hits = backtest(fn, klines, eval_dates)
        if not hits: continue
        r20 = [h['ret20'] for h in hits]
        win20 = sum(1 for r in r20 if r>0)/len(r20)*100
        print(f"{name:<12}: 命中={len(hits):<5} T+20均={statistics.mean(r20):.2f}%  T+20胜={win20:.1f}%")

if __name__ == "__main__": main()
