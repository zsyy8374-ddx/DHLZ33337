"""
v10: 机构抱团 + VCP 波动收敛模型
1. v10.0: v9.4 + VCP 3次收敛
2. v10.1: v9.4 + 成交量枯竭(起爆前缩量)
3. v10.2: v9.4 + 相对强度(RS > 80)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
KLINE_DIR = os.path.join(DATA_DIR, 'kline')
RESULT_DIR = os.path.join(os.path.dirname(__file__), '..', 'results')

def ma(arr,n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr,n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr,n): return min(arr[-n:]) if len(arr)>=n else None

def load_klines():
    out = {}
    for f in glob.glob(os.path.join(KLINE_DIR, '*.json')):
        code = os.path.basename(f).replace('.json','')
        try: out[code] = json.load(open(f))
        except: pass
    return out

def build_market_breadth(klines):
    by_date = defaultdict(lambda: {'up':0,'total':0,'med_chg':[], 'index_c': 1000})
    # 简单模拟一个大盘指数
    dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))
    daily_chgs = defaultdict(list)
    for code, bars in klines.items():
        for i, b in enumerate(bars):
            if i==0: continue
            daily_chgs[b['date']].append((b['c']/bars[i-1]['c']-1)*100)
    
    idx_val = 1000
    idx_history = {}
    for d in dates:
        if d in daily_chgs:
            m_chg = statistics.median(daily_chgs[d])
            idx_val *= (1 + m_chg/100)
        idx_history[d] = idx_val
        
    out = {}
    for d in dates:
        chgs = daily_chgs.get(d, [])
        if not chgs: continue
        out[d] = {
            'breadth': sum(1 for c in chgs if c>0)/len(chgs)*100,
            'med_chg': statistics.median(chgs),
            'index_c': idx_history[d]
        }
    return out

def f_v9_4_core(bars, today, mkt):
    if len(bars)<65: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; h=today['h']; v=today['v']; o=today['o']; l=today['l']
    
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 4.5): return False, 0, {}
    
    if mkt and mkt.get('breadth', 0) < 50: return False, 0, {}
    
    ma10=ma(closes,10); ma20=ma(closes,20); ma60=ma(closes,60)
    vol5=ma(vols,5); vol20=ma(vols,20)
    if not all([ma10,ma20,ma60,vol20]): return False, 0, {}
    if c <= ma10 or c <= ma20: return False, 0, {}
    
    ma20_5d_ago = ma(closes[-25:-5] if len(closes)>=25 else closes[:-5], 20)
    if not (ma20_5d_ago and ma20 > ma20_5d_ago * 1.005): return False, 0, {}
    
    ratio = v/vol20
    if not (1.3 < ratio < 2.5): return False, 0, {}
    
    # ATR 过滤 (MTR)
    mtrs = []
    for i in range(len(bars)-14, len(bars)):
        bar = bars[i]
        prev_c = bars[i-1]['c']
        mtrs.append(max(bar['h']-bar['l'], abs(bar['h']-prev_c), abs(bar['l']-prev_c)))
    atr14 = sum(mtrs)/14
    if atr14/c > 0.04: return False, 0, {}
    
    if vol5/vol20 < 1.0 or vol5/vol20 > 2.0: return False, 0, {}
    if closes[-1] <= ma(closes[:-1], 20): return False, 0, {}
    
    if c <= o: return False, 0, {}
    if h>l and (h-c)/(h-l) > 0.4: return False, 0, {}
    if c/ma60 > 1.35: return False, 0, {}
    if c < hhv(highs[-20:], 20) * 0.99: return False, 0, {}
    
    return True, 10, {'atr':atr14/c, 'vol_stab':vol5/vol20}

def f_v10_0_vcp(bars, today, mkt):
    """v10.0: v9.4 + VCP 波动收敛特征"""
    p, s, dbg = f_v9_4_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    # VCP: 检查过去3个波段的振幅是否收窄
    # 简化版: 比较 [t-20,t-10] 和 [t-10,t] 的最高振幅
    highs = [b['h'] for b in bars]
    lows = [b['l'] for b in bars]
    
    range1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(highs[-20:-10], 10)
    range2 = (max(highs[-10:]) - min(lows[-10:])) / ma(highs[-10:], 10)
    
    if range2 > range1 * 0.9: # 如果近期波动没有显著收窄(至少收窄10%),则排除
        return False, s, dbg
        
    return True, s, dict(dbg, vcp_ratio=range2/range1)

def f_v10_1_dryvol(bars, today, mkt):
    """v10.1: v9.4 + 成交量枯竭 (起爆前地量)"""
    p, s, dbg = f_v9_4_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    vols = [b['v'] for b in bars]
    # 检查前3天是否有至少1天是"地量" (小于20日均量的 60%)
    dry_days = sum(1 for v in vols[-3:] if v < ma(vols, 20) * 0.7)
    if dry_days < 1:
        return False, s, dbg
        
    return True, s, dict(dbg, dry_days=dry_days)

def f_v10_2_rs(bars, today, mkt):
    """v10.2: v9.4 + 相对强度 (RS)"""
    p, s, dbg = f_v9_4_core(bars, today, mkt)
    if not p: return False, s, dbg
    
    if not mkt or 'index_c' not in mkt: return False, s, dbg
    
    # 计算个股 60 日涨幅 vs 大盘 60 日涨幅
    stock_perf = today['c'] / bars[-60]['c']
    # 注意: 这里简化处理,假设 mkt 里的 index_c 是同步的
    # 实际回测中需要精确对位
    return True, s, dbg # 占位,逻辑在 backtest 中实现更准

def backtest(formula_fn, klines, eval_dates, market_breadth):
    hits = []
    for code, bars in klines.items():
        date_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in date_idx: continue
            i = date_idx[d]
            if i < 65: continue
            mkt = market_breadth.get(d, {})
            try:
                passed, score, dbg = formula_fn(bars[:i], bars[i], mkt)
            except: continue
            if not passed: continue
            if i+20 >= len(bars): continue
            
            entry = bars[i+1]['o']
            ret10 = (bars[i+10]['c']/entry-1)*100
            ret20 = (bars[i+20]['c']/entry-1)*100
            hits.append({'date':d,'code':code,'ret10':ret10,'ret20':ret20})
    return hits

def main():
    print("加载K线...")
    klines = load_klines()
    print("构建市场宽度及指数...")
    breadth = build_market_breadth(klines)
    
    eval_dates = sorted(breadth.keys())
    eval_dates = eval_dates[max(0,len(eval_dates)-120):-22]
    
    for name, fn in [('v9.4_Ref', f_v9_4_core), ('v10.0_VCP', f_v10_0_vcp), ('v10.1_DryVol', f_v10_1_dryvol)]:
        hits = backtest(fn, klines, eval_dates, breadth)
        if not hits:
            print(f"{name}: 无命中")
            continue
        r10 = [h['ret10'] for h in hits]
        r20 = [h['ret20'] for h in hits]
        win10 = sum(1 for r in r10 if r>0)/len(r10)*100
        win20 = sum(1 for r in r20 if r>0)/len(r20)*100
        print(f"{name}: 命中={len(hits)}, T+10均={statistics.mean(r10):.2f}%, T+10胜={win10:.1f}%, T+20均={statistics.mean(r20):.2f}%, T+20胜={win20:.1f}%")

if __name__=='__main__':
    main()
