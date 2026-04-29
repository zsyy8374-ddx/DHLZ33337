"""
v19: 超级能量释放 - 巨量突破半年新高
核心逻辑:
1. 创120日收盘新高
2. 成交量比 > 2.5 (巨量爆发)
3. 今日涨幅 > 7%
4. 价格距离120日线 < 40% (避开鱼尾)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None

def f_v19_power_breakout(bars, today, mkt):
    if len(bars)<120: return False, 0, {}
    closes=[b['c'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; v=today['v']
    
    # 1. 创 120 日新高
    h120 = hhv(closes, 120)
    if c <= h120: return False, 0, {}
    
    # 2. 巨量爆发 (> 2.5倍均量)
    v20 = ma(vols, 20)
    if not (v20 and v > v20 * 2.5): return False, 0, {}
    
    # 3. 强势涨幅 (> 7%)
    pct = (c/closes[-1]-1)*100
    if pct < 7: return False, 0, {}
    
    # 4. 趋势与距离
    m60 = ma(closes, 60); m120 = ma(closes, 120)
    if not (m60 and m120 and c > m60 > m120): return False, 0, {}
    if c / m120 > 1.4: return False, 0, {}
    
    return True, 100, {'pct': pct, 'vol_ratio': v/v20}

def backtest(formula_fn, klines, eval_dates):
    hits = []
    for code, bars in klines.items():
        d_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in d_idx: continue
            i = d_idx[d]
            if i < 120 or i+10 >= len(bars): continue
            passed, s, dbg = formula_fn(bars[:i], bars[i], None)
            if not passed: continue
            entry = bars[i+1]['o']
            hits.append({
                'date': d, 'code': code,
                'ret5': (bars[i+5]['c']/entry-1)*100,
                'ret10': (bars[i+10]['c']/entry-1)*100
            })
    return hits

def main():
    import glob, statistics
    print("正在进行 v19 超级能量释放版回测...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {os.path.basename(f).replace('.json',''): json.load(open(f)) for f in files}
    eval_dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))[120:-12]
    
    hits = backtest(f_v19_power_breakout, klines, eval_dates)
    if not hits:
        print("❌ v19 无命中")
        return

    r5 = [h['ret5'] for h in hits]
    r10 = [h['ret10'] for h in hits]
    win10 = sum(1 for r in r10 if r>0)/len(r10)*100
    avg10 = statistics.mean(r10)
    
    print(f"\n📊 v19 超级能量释放版结果 (总计 {len(hits)} 次命中):")
    print("-" * 40)
    print(f"T+5  均收益: {statistics.mean(r5):.2f}%")
    print(f"T+10 胜率: {win10:.1f}% 🏆")
    print(f"T+10 均收益: {avg10:.2f}%")
    print("-" * 40)
    
    # 排序看最猛的几只
    top_hits = sorted(hits, key=lambda x: x['ret10'], reverse=True)[:5]
    for h in top_hits:
        print(f"日期: {h['date']} | 代码: {h['code']} | T+10: {h['ret10']:.2f}%")

if __name__ == "__main__": main()
