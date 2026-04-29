"""
v18: 动量回踩 - 寻找强势股的第二次上车机会
核心逻辑:
1. 5日内有过大阳线 (>7%)
2. 均线多头 (5>10>20)
3. 缩量回踩 (今日量 < 5日均量*0.8)
4. 止跌 (今日收阳, 0.5% < 涨幅 < 3.5%)
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None

def f_v18_momentum_pullback(bars, today, mkt):
    if len(bars)<60: return False, 0, {}
    closes=[b['c'] for b in bars]; vols=[b['v'] for b in bars]; lows=[b['l'] for b in bars]
    c=today['c']; o=today['o']; v=today['v']
    
    # 1. 均线多头
    m5=ma(closes,5); m10=ma(closes,10); m20=ma(closes,20)
    if not (m5 and m10 and m20 and m5 > m10 > m20): return False, 0, {}
    
    # 2. 暴力基因 (5日内大阳)
    has_big_up = False
    for i in range(1, 6):
        prev_c = closes[-i-1]
        curr_c = closes[-i]
        if (curr_c/prev_c - 1) > 0.07:
            has_big_up = True
            break
    if not has_big_up: return False, 0, {}
    
    # 3. 缩量 (今日量 < 5日均量*0.8)
    m5v = ma(vols, 5)
    if v >= m5v * 0.8: return False, 0, {}
    
    # 4. 回踩 (最低价接近10日线)
    if not (today['l'] < m10 * 1.01 and c > m10): return False, 0, {}
    
    # 5. 止跌阳线 (0.5% < 涨幅 < 3.5%)
    today_pct = (c/closes[-1]-1)*100
    if not (0.5 < today_pct < 3.5 and c > o): return False, 0, {}
    
    return True, 100, {'pct': today_pct}

def backtest(formula_fn, klines, eval_dates):
    hits = []
    for code, bars in klines.items():
        d_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in d_idx: continue
            i = d_idx[d]
            if i < 60 or i+10 >= len(bars): continue
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
    print("正在进行 v18 动量回踩版全市场扫描...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {os.path.basename(f).replace('.json',''): json.load(open(f)) for f in files}
    eval_dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))[60:-12]
    
    hits = backtest(f_v18_momentum_pullback, klines, eval_dates)
    if not hits:
        print("❌ v18 无命中")
        return

    r10 = [h['ret10'] for h in hits]
    win10 = sum(1 for r in r10 if r>0)/len(r10)*100
    avg10 = statistics.mean(r10)
    
    print(f"\n📊 v18 动量回踩版结果 (总计 {len(hits)} 次命中):")
    print("-" * 40)
    print(f"T+10 胜率: {win10:.1f}% 🔥")
    print(f"T+10 均收益: {avg10:.2f}%")
    print("-" * 40)
    
    # 打印今日 (4/27) 如果有的话
    today_hits = [h for h in hits if h['date'] == '2026-04-27']
    print(f"今日 (4/27) 命中数: {len(today_hits)}")
    for h in today_hits:
        print(f"代码: {h['code']}")

if __name__ == "__main__": main()
