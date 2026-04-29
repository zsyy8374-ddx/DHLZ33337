"""
v16: 极度苛刻版 - 寻找 1% 的真主升浪
核心逻辑:
1. 极窄 VCP (波动收缩比 < 0.3): 最近 10 天波动必须只有之前 10 天的 1/3。
2. 能量枯竭 (成交量比 < 1.1): 启动当天不许爆量，只要温和放量。
3. 底部抬升: 5日均线必须斜率向上 > 20度。
4. 筹码全获利: 必须站上所有均线 (10, 20, 60, 120)。
"""
import json, os, glob, statistics
from collections import defaultdict

DATA_DIR = 'backtest/data'
KLINE_DIR = os.path.join(DATA_DIR, 'kline')

def ma(arr, n): return sum(arr[-n:])/n if len(arr)>=n else None
def hhv(arr, n): return max(arr[-n:]) if len(arr)>=n else None
def llv(arr, n): return min(arr[-n:]) if len(arr)>=n else None

def f_v16_extreme(bars, today, mkt):
    if len(bars)<120: return False, 0, {}
    closes=[b['c'] for b in bars]; highs=[b['h'] for b in bars]
    lows=[b['l'] for b in bars]; vols=[b['v'] for b in bars]
    c=today['c']; o=today['o']; h=today['h']; l=today['l']
    
    # 1. 基础门槛: 站上四线 (10, 20, 60, 120)
    m10=ma(closes,10); m20=ma(closes,20); m60=ma(closes,60); m120=ma(closes,120)
    if not all([m10,m20,m60,m120]): return False, 0, {}
    if c < m10 or c < m20 or c < m60 or c < m120: return False, 0, {}
    
    # 2. 极致 VCP (收缩比 < 0.3)
    w1 = (max(highs[-20:-10]) - min(lows[-20:-10])) / ma(closes[-20:-10], 10)
    w2 = (max(highs[-10:]) - min(lows[-10:])) / ma(closes[-10:], 10)
    if w1 == 0: return False, 0, {}
    vcp_ratio = w2 / w1
    if vcp_ratio > 0.3: return False, 0, {} # 极度苛刻
    
    # 3. 极窄整理带 (最近10天总波幅 < 6%)
    if (max(highs[-10:]) - min(lows[-10:])) / m10 > 0.06: return False, 0, {}
    
    # 4. 今日动向: 温和启动 (1.5% < 涨幅 < 3.5%)
    today_pct = (c/closes[-1]-1)*100
    if not (1.5 < today_pct < 3.5): return False, 0, {}
    
    # 5. 成交量控制: 绝不许爆量 (量比 1.1 - 1.6)
    vol20 = ma(vols, 20)
    ratio = today['v'] / vol20
    if not (1.1 < ratio < 1.6): return False, 0, {}
    
    # 6. 趋势斜率: 5日均线向上
    m5_now = ma(closes + [c], 5)
    m5_prev = ma(closes, 5)
    if m5_now <= m5_prev: return False, 0, {}
    
    return True, 100, {'vcp': vcp_ratio, 'ratio': ratio, 'pct': today_pct}

def backtest(formula_fn, klines, eval_dates):
    hits = []
    for code, bars in klines.items():
        d_idx = {b['date']:i for i,b in enumerate(bars)}
        for d in eval_dates:
            if d not in d_idx: continue
            i = d_idx[d]
            if i < 120 or i+20 >= len(bars): continue
            passed, s, dbg = formula_fn(bars[:i], bars[i], None)
            if not passed: continue
            entry = bars[i+1]['o']
            hits.append({
                'date': d, 'code': code,
                'ret5': (bars[i+5]['c']/entry-1)*100,
                'ret10': (bars[i+10]['c']/entry-1)*100,
                'ret20': (bars[i+20]['c']/entry-1)*100,
                'dbg': dbg
            })
    return hits

def main():
    import glob, statistics
    print("正在对 1494 只股票进行极度苛刻回测...")
    files = glob.glob(os.path.join(KLINE_DIR, '*.json'))
    klines = {os.path.basename(f).replace('.json',''): json.load(open(f)) for f in files}
    
    dates = sorted(list(set(b['date'] for bars in klines.values() for b in bars)))
    eval_dates = dates[120:-22]
    
    hits = backtest(f_v16_extreme, klines, eval_dates)
    
    if not hits:
        print("❌ v16 极端版在回测期内无任何命中! 条件太严。")
        return

    r5 = [h['ret5'] for h in hits]
    r10 = [h['ret10'] for h in hits]
    r20 = [h['ret20'] for h in hits]
    
    print(f"\n✅ v16 极端版结果 (总计 {len(hits)} 次命中):")
    print("-" * 60)
    print(f"T+5  均收益: {statistics.mean(r5):.2f}% | 胜率: {sum(1 for r in r5 if r>0)/len(r5)*100:.1f}%")
    print(f"T+10 均收益: {statistics.mean(r10):.2f}% | 胜率: {sum(1 for r in r10 if r>0)/len(r10)*100:.1f}%")
    print(f"T+20 均收益: {statistics.mean(r20):.2f}% | 胜率: {sum(1 for r in r20 if r>0)/len(r20)*100:.1f}%")
    print("-" * 60)
    
    # 打印部分命中记录用于分析
    print("\n样例标的分析:")
    for h in hits[:5]:
        print(f"日期: {h['date']} | 代码: {h['code']} | T+20回报: {h['ret20']:.2f}%")

if __name__ == "__main__": main()
